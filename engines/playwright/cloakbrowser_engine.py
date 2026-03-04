import asyncio
import logging
import os
from typing import Dict, Optional, Literal, List

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

    async def start(self) -> None:
        self._start_time = asyncio.get_event_loop().time()

        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        launch_options: Dict[str, object] = {
            "headless": self.get_effective_headless(),
        }

        if self.proxy:
            launch_options["proxy"] = {
                "server": f"{self.proxy['protocol']}://{self.proxy['host']}:{self.proxy['port']}",
            }
            if "username" in self.proxy and "password" in self.proxy:
                launch_options["proxy"]["username"] = self.proxy["username"]
                launch_options["proxy"]["password"] = self.proxy["password"]

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
