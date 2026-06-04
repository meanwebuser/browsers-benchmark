import logging
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
        logger.info("DAMRU engine %s started in %.0f ms", self.name, self.startup_ms)

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
