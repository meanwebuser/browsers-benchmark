import asyncio
import logging
import os
from typing import Dict, Optional, List

import psutil
import zendriver as zd
from zendriver import cdp as zendriver_cdp
from zendriver.cdp import fetch

from config.settings import settings
from engines.nodriver_base import NoDriverBase
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)


class ZenDriverEngine(NoDriverBase):
    def __init__(
            self,
            name: str = "zendriver-chrome",

            user_agent: Optional[str] = None,
            headless: bool = True,

            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        """
        Initialize the ZenDriverEngine with the given parameters

        :param name: Name of the engine instance
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        super().__init__(name, user_agent, headless, proxy, init_scripts=init_scripts, **kwargs)

        self.browser: Optional[zd.Browser] = None
        self.page: Optional[zd.Tab] = None

    @property
    def supported_proxy_protocols(self) -> list[str]:
        return ["http", "https"]

    @staticmethod
    async def setup_proxy(username, password, main_tab):
        main_loop = asyncio.get_running_loop()

        def auth_challenge_handler(event: fetch.AuthRequired):
            try:
                asyncio.run_coroutine_threadsafe(
                    asyncio.wait_for(main_tab.send(
                        fetch.continue_with_auth(
                            request_id=event.request_id,
                            auth_challenge_response=fetch.AuthChallengeResponse(
                                response="ProvideCredentials",
                                username=username,
                                password=password,
                            ),
                        )
                    ), timeout=settings.browser.action_timeout_s),
                    main_loop
                )
            except Exception as e:
                logger.error(f"Error in auth challenge handler: {e}")

        def req_paused(event: fetch.RequestPaused):
            try:
                asyncio.run_coroutine_threadsafe(
                    asyncio.wait_for(main_tab.send(fetch.continue_request(request_id=event.request_id)),
                                     timeout=settings.browser.action_timeout_s),
                    main_loop
                )
            except Exception as e:
                logger.error(f"Error continuing request: {e}")

        main_tab.add_handler(
            fetch.RequestPaused, lambda event, connection: req_paused(event)
        )
        main_tab.add_handler(
            fetch.AuthRequired,
            lambda event, connection: auth_challenge_handler(event)
        )

        # enable fetch domain with auth requests handling
        await main_tab.send(fetch.enable(handle_auth_requests=True))

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        try:
            # create context with proxy configuration if provided
            browser_args = []
            effective_headless = self.headless

            if not effective_headless and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                logger.warning(
                    "%s requested headed mode without display server; forcing headless mode.",
                    self.name
                )
                effective_headless = True

            if self.proxy:
                proxy_server = f"{self.proxy['host']}:{self.proxy['port']}"

                # add protocol prefix
                protocol = self.proxy.get('protocol', 'http')
                proxy_url = f"{protocol}://{proxy_server}"

                browser_args.append(f'--proxy-server={proxy_url}')

            if effective_headless:
                browser_args.append('--headless=new')  # use new headless mode

            if self.user_agent:
                browser_args.append(f'--user-agent="{self.user_agent}"')

            # start browser with zendriver
            self.browser = await asyncio.wait_for(zd.start(
                headless=effective_headless,
                browser_args=browser_args,
                user_data_dir=None,  # use temporary profile
                sandbox=False
            ),
                timeout=settings.browser.action_timeout_s)

            main_tab = await self.browser.get("about:blank")

            if self.proxy and self.proxy.get('username') and self.proxy.get('password'):
                await self.setup_proxy(self.proxy.get('username'), self.proxy.get('password'), main_tab)

            self.page = main_tab
            await self._apply_init_scripts()

            logger.info(f"ZenDriver browser started successfully: {self.name}")
        except Exception as e:
            logger.error(f"Failed to start ZenDriver browser: {e}")
            if await self._start_playwright_fallback(e):
                return
            raise

        await self.ensure_proxy_is_used()

        # track process for resource usage
        process_children_after = parent_process.children(recursive=True)
        process_children_filtered = find_new_child_processes(process_children_before, process_children_after)
        self.process_list = process_children_filtered

    async def stop(self) -> None:
        """Stop the browser and clean up resources"""

        if self._fallback_engine:
            try:
                await self._fallback_engine.stop()
            except Exception as e:
                logger.debug("Error stopping fallback engine: %s", e)
            finally:
                self._fallback_engine = None
                self.process_list = None
            return

        try:
            if self.browser:
                await asyncio.wait_for(self.browser.stop(),
                                       timeout=settings.browser.action_timeout_s)
        except Exception as e:
            logger.debug(f"Error stopping browser: {e}")

        self.browser = None
        self.page = None
        self.process_list = None

    async def _apply_init_scripts(self) -> None:
        if not self.page or not self.init_scripts:
            return

        for script_file in self.init_scripts:
            script_content = await load_js_script(
                script_file,
                user_agent=self.user_agent,
                browser_type="chrome",
            )
            try:
                await asyncio.wait_for(
                    self.page.send(
                        zendriver_cdp.page.add_script_to_evaluate_on_new_document(source=script_content)
                    ),
                    timeout=settings.browser.action_timeout_s,
                )
            except Exception as e:
                logger.warning(
                    "Failed to register init script '%s' in %s: %s",
                    script_file,
                    self.name,
                    e,
                )
