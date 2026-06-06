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
        logger.info("DAMRU engine %s started in %.0f ms (adb_serial=%s, chrome_pid=%s)",
                     self.name, self.startup_ms, self._adb_serial, self._chrome_pid)

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

    def get_memory_usage(self) -> int:
        if not self._adb_serial or not self._chrome_pid:
            return 0
        try:
            import subprocess
            result = subprocess.run(
                ["adb", "-s", self._adb_serial, "shell",
                 f"cat /proc/{self._chrome_pid}/status 2>/dev/null | grep VmRSS"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                match = re.search(r"(\d+)\s+kB", result.stdout)
                if match:
                    return int(match.group(1)) // 1024
        except Exception as e:
            logger.debug("Failed to get Chrome memory via ADB: %s", e)
        return 0

    def get_cpu_usage(self) -> float:
        if not self._adb_serial or not self._chrome_pid:
            return 0.0
        try:
            import subprocess
            result1 = subprocess.run(
                ["adb", "-s", self._adb_serial, "shell",
                 f"cat /proc/{self._chrome_pid}/stat 2>/dev/null | cut -d' ' -f14"],
                capture_output=True, text=True, timeout=10,
            )
            import time
            time.sleep(0.1)
            result2 = subprocess.run(
                ["adb", "-s", self._adb_serial, "shell",
                 f"cat /proc/{self._chrome_pid}/stat 2>/dev/null | cut -d' ' -f14"],
                capture_output=True, text=True, timeout=10,
            )
            utime1 = int(result1.stdout.strip()) if result1.stdout.strip().isdigit() else 0
            utime2 = int(result2.stdout.strip()) if result2.stdout.strip().isdigit() else 0
            clk_tck = 100
            cpu_percent = (utime2 - utime1) / clk_tck / 0.1 * 100
            return min(cpu_percent, 100.0)
        except Exception as e:
            logger.debug("Failed to get Chrome CPU via ADB: %s", e)
        return 0.0

    async def screenshot(self, path: str) -> None:
        if not self.page:
            raise RuntimeError("browser not started")
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
