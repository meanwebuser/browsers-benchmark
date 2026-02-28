import asyncio
import os
from typing import Dict, Optional, Literal, List

import psutil
from camoufox.async_api import AsyncCamoufox

from config.settings import settings
from engines.playwright_base import PlaywrightBase
from utils.js_script import load_js_script
from utils.process import find_new_child_processes


class CamoufoxEngine(PlaywrightBase):
    def __init__(
            self,
            name: str = "camoufox",

            user_agent: Optional[str] = None,
            headless: bool = True,

            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        """
        Initialize the CamoufoxEngine with the given parameters

        :param name: Name of the engine instance
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        browser_type: Literal['chromium', 'firefox', 'webkit'] = 'firefox'  # camoufox only supports firefox
        super().__init__(
            name,
            browser_type,
            user_agent,
            headless,
            proxy,
            init_scripts=init_scripts,
        )

        self.camoufox = None

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        # configure launch options
        launch_options = {}

        if self.proxy:
            launch_options["proxy"] = {
                "server": f"{self.proxy['protocol']}://{self.proxy['host']}:{self.proxy['port']}",
            }
            if "username" in self.proxy and "password" in self.proxy:
                launch_options["proxy"]["username"] = self.proxy["username"]
                launch_options["proxy"]["password"] = self.proxy["password"]

        effective_headless = self.get_effective_headless()
        self.camoufox = AsyncCamoufox(headless=effective_headless, geoip=True, **launch_options)
        await self.camoufox.start()

        self.browser = self.camoufox.browser

        # create context and page; user agent must be set at context level
        context_options = {}
        if self.user_agent:
            context_options["user_agent"] = self.user_agent

        self.context = await self.browser.new_context(**context_options)
        await self.context.add_init_script(await load_js_script('unlockShadowDom.js'))
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

        # track process for resource usage
        process_children_after = parent_process.children(recursive=True)
        process_children_filtered = find_new_child_processes(process_children_before, process_children_after)
        self.process_list = process_children_filtered

    async def stop(self) -> None:
        """Stop the browser and clean up resources"""

        try:
            if self.page:
                await self.page.close()
        except:
            pass
        self.page = None

        try:
            if self.context:
                await self.context.close()
        except:
            pass
        self.context = None

        try:
            if self.browser:
                await self.browser.close()
        except:
            pass
        self.browser = None

        try:
            if self.camoufox:
                await self.camoufox.__aexit__()
        except:
            pass
        self.camoufox = None

        self._stop_virtual_display()
        self.process_list = None
