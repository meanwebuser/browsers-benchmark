import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

from damru.async_core import AsyncDamru

from config.settings import settings
from engines.playwright_base import PlaywrightBase

logger = logging.getLogger(__name__)


class DamruEngine(PlaywrightBase):
    """Browser benchmark adapter for DAMRU Android Chrome automation.

    DAMRU exposes an async context manager that returns a Playwright
    BrowserContext connected to Android Chrome over CDP.  The benchmark can
    reuse the standard Playwright navigation, JS, screenshot and locator logic
    once this adapter assigns ``self.context`` and ``self.page``.
    """

    supports_stealth_variants = False

    def __init__(
        self,
        name: str = "damru",
        browser_type: str = "android-chrome",
        user_agent: Optional[str] = None,
        headless: Optional[bool] = None,
        proxy: Optional[Dict[str, str]] = None,
        device: Optional[str] = None,
        serial: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        chrome_package: Optional[str] = None,
        restore_props: bool = True,
        debug: bool = False,
        **kwargs: Any,
    ):
        super().__init__(
            name=name,
            browser_type="chromium",
            user_agent=user_agent,
            headless=True,
            proxy=proxy,
            **kwargs,
        )
        self.browser_type = browser_type
        self.headless = True
        self.device = device
        self.serial = serial
        self.timezone = timezone
        self.locale = locale
        self.chrome_package = chrome_package
        self.restore_props = restore_props
        self.debug = debug
        self._damru: Optional[AsyncDamru] = None
        self._start_time: Optional[float] = None
        self._adb_serial: Optional[str] = None
        self._chrome_pid: Optional[int] = None
        self._container_id: Optional[str] = None
        self._prev_cpu: Optional[int] = None
        self._prev_cpu_ts: Optional[float] = None

    @property
    def supported_proxy_protocols(self) -> list[str]:
        return ["http", "https", "socks5"]

    def _proxy_url(self) -> Optional[str]:
        if not self.proxy:
            return None
        server = self.proxy.get("server") or self.proxy.get("host")
        if server and "://" in server:
            return server
        protocol = (self.proxy.get("protocol") or "http").replace(":", "")
        host = self.proxy.get("host") or server
        port = self.proxy.get("port")
        username = self.proxy.get("username")
        password = self.proxy.get("password")
        if not host:
            return None
        auth = f"{username}:{password}@" if username and password else ""
        return f"{protocol}://{auth}{host}:{port}" if port else f"{protocol}://{auth}{host}"

    async def start(self) -> None:
        self._start_time = time.time()
        proxy_url = self._proxy_url()
        logger.info("Starting DAMRU engine %s", self.name)
        if proxy_url:
            logger.info("DAMRU proxy enabled for %s", self.name)

        self._damru = AsyncDamru(
            device=self.device,
            serial=self.serial,
            proxy=proxy_url,
            timezone=self.timezone,
            locale=self.locale,
            chrome_package=self.chrome_package,
            restore_props=self.restore_props,
            debug=self.debug,
        )
        self.context = await self._damru.__aenter__()

        pages = list(self.context.pages)
        self.page = pages[0] if pages else await self.context.new_page()
        self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
        self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)
        self.browser = getattr(self.context, "browser", None)
        self.startup_ms = (time.time() - self._start_time) * 1000

        self._adb_serial = getattr(self._damru, "_serial", self.serial)
        await self._resolve_chrome_pid()
        await self._detect_container()
        logger.info("DAMRU engine %s started in %.0f ms (adb_serial=%s, chrome_pid=%s, container=%s)",
                     self.name, self.startup_ms, self._adb_serial, self._chrome_pid, self._container_id)

    async def _adb_shell(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", self._adb_serial, "shell", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            raise RuntimeError(f"adb shell failed (rc={proc.returncode}): {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def _resolve_chrome_pid(self) -> None:
        if not self._adb_serial:
            return
        try:
            pkg = self.chrome_package or "com.android.chrome"
            out = await self._adb_shell(f"pidof {pkg}")
            pids = [int(p) for p in out.split() if p.strip().isdigit()]
            if pids:
                self._chrome_pid = pids[0]
        except Exception as e:
            logger.debug("Failed to resolve Chrome PID via ADB: %s", e)

    async def _detect_container(self) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "ps", "--filter", "name=damru", "--format", "{{.ID}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            cid = stdout.decode().strip().split("\n")[0] if stdout else ""
            if cid:
                self._container_id = cid[:12]
        except Exception as e:
            logger.debug("Failed to detect Docker container: %s", e)

    def _container_memory_mb(self) -> int:
        if not self._container_id:
            return 0
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", self._container_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                mem_str = result.stdout.strip().split("/")[0].strip()
                if mem_str.endswith("MiB"):
                    return int(float(mem_str.replace("MiB", "")))
                if mem_str.endswith("GiB"):
                    return int(float(mem_str.replace("GiB", "")) * 1024)
        except Exception as e:
            logger.debug("Failed to get container memory: %s", e)
        return 0

    def get_memory_usage(self) -> int:
        return self._container_memory_mb()

    def get_cpu_usage(self) -> float:
        if not self._container_id:
            return 0.0
        try:
            import subprocess
            import time
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", self._container_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                cpu_str = result.stdout.strip().replace("%", "")
                return float(cpu_str) if cpu_str else 0.0
        except Exception as e:
            logger.debug("Failed to get container CPU: %s", e)
        return 0.0

    async def _ensure_alive(self) -> bool:
        """Check if page/context is alive; try to reconnect if dead."""
        if self.page is None or self.context is None:
            return False
        try:
            await self.page.evaluate("1")
            return True
        except Exception:
            pass
        try:
            pages = list(self.context.pages)
            if pages:
                self.page = pages[0]
                self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
                self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)
                await self.page.evaluate("1")
                return True
        except Exception:
            pass
        try:
            self.context = await self._damru.reconnect_cdp()
            pages = list(self.context.pages) or [await self.context.new_page()]
            self.page = pages[0]
            self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
            self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)
            logger.info("CDP reconnected successfully")
            return True
        except Exception as e:
            logger.warning("CDP reconnect failed: %s", e)
            return False

    async def screenshot(self, path: str) -> None:
        if not self.page:
            raise RuntimeError("browser not started")
        await self._ensure_alive()
        await self.page.screenshot(path=path, timeout=15000)

    async def stop(self) -> None:
        logger.info("Stopping DAMRU engine %s", self.name)
        try:
            if self._damru:
                await self._damru.__aexit__(None, None, None)
        finally:
            self._damru = None
            self.page = None
            self.context = None
            self.browser = None
