import asyncio
import json
import logging
import os
from collections import deque
from typing import Any, Dict, Optional, Tuple, List

import psutil

from config.settings import settings
from engines.base import BrowserEngine, NavigationResult
from utils.js_script import load_js_script

logger = logging.getLogger(__name__)


class UlixeeHeroEngine(BrowserEngine):
    def __init__(
            self,
            name: str = "ulixee-hero_headless",
            user_agent: Optional[str] = None,
            headless: bool = True,
            viewport_width: int = 1366,
            viewport_height: int = 768,
            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        super().__init__(name, proxy)
        self.user_agent = user_agent
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.init_scripts = init_scripts or []

        self._worker: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._io_lock = asyncio.Lock()
        self._command_id = 0
        self._stderr_buffer: deque[str] = deque(maxlen=50)

    @property
    def supported_proxy_protocols(self) -> list[str]:
        return ["http", "https"]

    async def start(self) -> None:
        self._start_time = asyncio.get_event_loop().time()

        worker_path = os.path.join(os.path.dirname(__file__), "hero_worker.js")
        if not os.path.exists(worker_path):
            raise FileNotFoundError(f"{self.name}: Hero worker file is missing: {worker_path}")

        self._worker = await asyncio.create_subprocess_exec(
            "node",
            worker_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            init_script_sources: List[str] = []
            for script_file in self.init_scripts:
                init_script_sources.append(
                    await load_js_script(
                        script_file,
                        user_agent=self.user_agent,
                        browser_type="chrome",
                    )
                )
            await self._send_command(
                "start",
                {
                    "headless": self.headless,
                    "userAgent": self.user_agent,
                    "viewport": {"width": self.viewport_width, "height": self.viewport_height},
                    "proxy": self.proxy,
                    "pageLoadTimeoutMs": settings.browser.page_load_timeout_s * 1000,
                    "initScripts": init_script_sources,
                },
                timeout_s=max(10, settings.browser.action_timeout_s),
            )
        except Exception:
            await self.stop()
            raise

        await self.ensure_proxy_is_used()

        if self._worker and self._worker.pid:
            self.process_list = [psutil.Process(self._worker.pid)]
        else:
            self.process_list = []

    async def stop(self) -> None:
        try:
            if self._worker and self._worker.returncode is None:
                try:
                    await self._send_command("stop", {}, timeout_s=5)
                except Exception:
                    pass
        finally:
            if self._worker and self._worker.returncode is None:
                self._worker.terminate()
                try:
                    await asyncio.wait_for(self._worker.wait(), timeout=5)
                except Exception:
                    self._worker.kill()
                    try:
                        await self._worker.wait()
                    except Exception:
                        pass

            if self._stderr_task:
                self._stderr_task.cancel()
                try:
                    await self._stderr_task
                except Exception:
                    pass

            self._stderr_task = None
            self._worker = None
            self.process_list = None

    async def navigate(self, url: str) -> NavigationResult:
        result = await self._send_command(
            "navigate",
            {"url": url, "timeoutMs": settings.browser.page_load_timeout_s * 1000},
            timeout_s=settings.browser.page_load_timeout_s + 15,
        )
        return {
            "url": result.get("url", url),
            "load_time": float(result.get("load_time", 0.0)),
            "success": bool(result.get("success", False)),
            "headers": result.get("headers", {}) or {},
        }

    async def reload_page(self) -> NavigationResult:
        result = await self._send_command(
            "reload",
            {"timeoutMs": settings.browser.page_load_timeout_s * 1000},
            timeout_s=settings.browser.page_load_timeout_s + 15,
        )
        return {
            "url": result.get("url", ""),
            "load_time": float(result.get("load_time", 0.0)),
            "success": bool(result.get("success", False)),
            "headers": result.get("headers", {}) or {},
        }

    async def locator(self, css_selector: str) -> Tuple[bool, str]:
        result = await self._send_command(
            "locator",
            {"selector": css_selector},
            timeout_s=settings.browser.action_timeout_s,
        )
        return bool(result.get("found", False)), str(result.get("html", "") or "")

    async def get_page_content(self) -> str:
        result = await self._send_command(
            "get_page_content",
            {},
            timeout_s=settings.browser.action_timeout_s,
        )
        return str(result.get("content", "") or "")

    async def execute_js(self, script: str) -> Any:
        result = await self._send_command(
            "execute_js",
            {"script": script},
            timeout_s=settings.browser.action_timeout_s,
        )
        return result.get("value")

    async def screenshot(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await self._send_command(
            "screenshot",
            {"path": path},
            timeout_s=settings.browser.action_timeout_s,
        )

    async def _send_command(self, command: str, payload: Dict[str, Any], timeout_s: int) -> Dict[str, Any]:
        async with self._io_lock:
            if not self._worker or self._worker.returncode is not None:
                raise RuntimeError(f"{self.name}: Hero worker is not running")
            if not self._worker.stdin or not self._worker.stdout:
                raise RuntimeError(f"{self.name}: Hero worker pipes are not available")

            self._command_id += 1
            request = {"id": self._command_id, "command": command, "payload": payload}
            self._worker.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._worker.stdin.drain()

            response = await asyncio.wait_for(
                self._read_response(expected_id=self._command_id),
                timeout=timeout_s,
            )
            if not response.get("ok", False):
                error_text = response.get("error", "Unknown worker error")
                raise RuntimeError(f"{self.name}: worker command '{command}' failed: {error_text}")

            return response.get("result", {}) or {}

    async def _read_response(self, expected_id: int) -> Dict[str, Any]:
        if not self._worker or not self._worker.stdout:
            raise RuntimeError(f"{self.name}: worker stdout is unavailable")

        while True:
            raw_line = await self._worker.stdout.readline()
            if not raw_line:
                stderr_tail = "\n".join(self._stderr_buffer)
                raise RuntimeError(
                    f"{self.name}: Hero worker closed stdout unexpectedly."
                    + (f"\nRecent stderr:\n{stderr_tail}" if stderr_tail else "")
                )

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("%s worker stdout (non-json): %s", self.name, line)
                continue

            if payload.get("id") != expected_id:
                logger.debug(
                    "%s received out-of-order worker response id=%s (expected=%s)",
                    self.name,
                    payload.get("id"),
                    expected_id,
                )
                continue

            return payload

    async def _drain_stderr(self) -> None:
        if not self._worker or not self._worker.stderr:
            return

        while True:
            line = await self._worker.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip()
            self._stderr_buffer.append(text)
            logger.debug("%s worker stderr: %s", self.name, text)
