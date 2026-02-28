import asyncio
import logging
import os
from typing import Dict, Optional, Literal, List

import psutil
from patchright.async_api import async_playwright, BrowserType

from config.settings import settings
from engines.playwright_base import PlaywrightBase
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)


class PatchrightEngine(PlaywrightBase):
    def __init__(
            self,
            name: str = "patchright",

            user_agent: Optional[str] = None,
            headless: bool = True,

            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        """
        Initialize the PatchrightEngine with the given parameters

        :param name: Name of the engine instance
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        browser_type: Literal['chromium', 'firefox', 'webkit'] = 'chromium'  # patchright only supports chromium
        super().__init__(
            name,
            browser_type,
            user_agent,
            headless,
            proxy,
            init_scripts=init_scripts,
        )
        self._runtime_init_scripts: List[str] = []

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        # initialize playwright
        self.playwright = await async_playwright().start()
        browser_launcher: BrowserType = self.playwright.chromium

        # configure browser context
        context_options = {}

        if self.user_agent:
            context_options["user_agent"] = self.user_agent

        if self.proxy:
            context_options["proxy"] = {
                "server": f"{self.proxy['protocol']}://{self.proxy['host']}:{self.proxy['port']}",
            }
            if "username" in self.proxy and "password" in self.proxy:
                context_options["proxy"]["username"] = self.proxy["username"]
                context_options["proxy"]["password"] = self.proxy["password"]

        # create context and page
        effective_headless = self.get_effective_headless()
        try:
            self.context = await browser_launcher.launch_persistent_context(
                user_data_dir="",
                channel="chrome",
                headless=effective_headless,
                no_viewport=effective_headless,
                **context_options
            )
        except Exception as e:
            if not effective_headless and self._is_missing_display_error(e):
                logger.warning(
                    "%s failed to start in headed mode due to display issue; retrying in headless mode.",
                    self.name
                )
                self.context = await browser_launcher.launch_persistent_context(
                    user_data_dir="",
                    channel="chrome",
                    headless=True,
                    no_viewport=True,
                    **context_options
                )
            else:
                raise
        self.page = await self.context.new_page()

        self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
        self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)
        # NOTE:
        # Patchright persistent contexts can break all outbound navigation when using add_init_script.
        # Keep scripts for runtime injection after navigation instead.
        self._runtime_init_scripts = [await load_js_script("unlockShadowDom.js")]
        for script_file in self.init_scripts:
            self._runtime_init_scripts.append(
                await load_js_script(
                    script_file,
                    user_agent=self.user_agent,
                    browser_type=self.browser_type,
                )
            )

        await self.ensure_proxy_is_used()

        # track process for resource usage
        process_children_after = parent_process.children(recursive=True)
        process_children_filtered = find_new_child_processes(process_children_before, process_children_after)
        self.process_list = process_children_filtered

    async def _apply_runtime_init_scripts(self) -> None:
        if not self._runtime_init_scripts:
            return
        for script in self._runtime_init_scripts:
            try:
                await self.execute_js(script)
            except Exception as e:
                logger.warning("%s failed to execute runtime init script: %s", self.name, e)

    async def navigate(self, url: str) -> Dict[str, object]:
        result = await super().navigate(url)
        await self._apply_runtime_init_scripts()
        return result

    async def reload_page(self):
        result = await super().reload_page()
        await self._apply_runtime_init_scripts()
        return result
