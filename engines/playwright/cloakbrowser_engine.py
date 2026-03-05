import asyncio
import logging
import os
from typing import Dict, Optional, Literal, List
from urllib.parse import quote

import psutil
from cloakbrowser import launch_async

from config.settings import settings
from engines.playwright_base import PlaywrightBase
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)


class CloakBrowserEngine(PlaywrightBase):
    def __init__(
            self,
            name: str = "cloakbrowser",
            user_agent: Optional[str] = None,
            headless: bool = True,
            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            geoip: bool = True,
            locale: Optional[str] = None,
            timezone: Optional[str] = None,
            **kwargs
    ):
        browser_type: Literal['chromium', 'firefox', 'webkit'] = 'chromium'
        super().__init__(
            name,
            browser_type,
            user_agent,
            headless,
            proxy,
            init_scripts=init_scripts,
        )
        self.geoip = geoip
        self.locale = locale
        self.timezone = timezone

    async def start(self) -> None:
        self._start_time = asyncio.get_event_loop().time()

        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        launch_options: Dict[str, object] = {
            "headless": self.get_effective_headless(),
            "geoip": self.geoip,
        }
        if self.locale:
            launch_options["locale"] = self.locale
        if self.timezone:
            launch_options["timezone"] = self.timezone

        if self.proxy:
            launch_options["proxy"] = self._build_cloakbrowser_proxy()

        self.browser = await launch_async(**launch_options)
        context_options: Dict[str, object] = {}
        if self.user_agent:
            context_options["user_agent"] = self.user_agent
        self.context = await self.browser.new_context(**context_options)
        for script_file in self.init_scripts:
            await self.context.add_init_script(
                await load_js_script(
                    script_file,
                    user_agent=self.user_agent,
                    browser_type=self.browser_type,
                )
            )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
        self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)

        await self.ensure_proxy_is_used()

        process_children_after = parent_process.children(recursive=True)
        self.process_list = find_new_child_processes(process_children_before, process_children_after)

    async def reload_page(self):
        """
        Reload the current page.

        CloakBrowser may occasionally never resolve Playwright's reload navigation wait.
        In that case, fallback to JS-triggered reload and wait for readyState.
        """

        if not self.page:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()
        response = None
        success = False

        try:
            response = await self.page.reload(timeout=settings.browser.page_load_timeout_s * 1000)
            success = response.ok if response else False
        except Exception:
            try:
                await self.page.evaluate("window.location.reload();")
                await self.page.wait_for_function(
                    "() => document.readyState === 'complete'",
                    timeout=settings.browser.page_load_timeout_s * 1000,
                )
                success = True
            except Exception:
                success = False

        end_time = asyncio.get_event_loop().time()
        return {
            "url": self.page.url if self.page else "",
            "load_time": end_time - start_time,
            "success": success,
            "headers": response.headers if response else {},
        }

    def _build_cloakbrowser_proxy(self) -> str:
        if not self.proxy:
            raise ValueError("Proxy configuration is required.")

        protocol = str(self.proxy.get("protocol", "http"))
        host = self.proxy.get("host")
        port = self.proxy.get("port")
        username = self.proxy.get("username")
        password = self.proxy.get("password")

        if not host or not port:
            raise ValueError("Proxy host and port are required when proxy is configured.")

        if username and password:
            escaped_user = quote(str(username), safe="")
            escaped_pass = quote(str(password), safe="")
            return f"{protocol}://{escaped_user}:{escaped_pass}@{host}:{port}"
        return f"{protocol}://{host}:{port}"

    async def stop(self) -> None:
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass
        self.page = None

        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        self.context = None

        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        self.browser = None

        self._stop_virtual_display()
        self.process_list = None
