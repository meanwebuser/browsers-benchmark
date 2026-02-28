import asyncio
import logging
import os
from typing import Dict, Optional, Any, Tuple, List

import nodriver as uc
from nodriver import cdp as nodriver_cdp
import psutil

from config.settings import settings
from engines.base import BrowserEngine, NavigationResult
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)

"""
asyncio.wait_for is used to implement a timeout for page navigation
because NoDriver doesn't support timeout natively (as far as I see)
"""


class NoDriverBase(BrowserEngine):
    def __init__(
            self,
            name: str = "nodriver-chrome",

            user_agent: Optional[str] = None,
            headless: bool = True,

            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        """
        Initialize the NoDriverBase with the given parameters

        :param name: Name of the engine instance
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        super().__init__(name, proxy)
        self.user_agent = user_agent
        self.headless = headless
        self.init_scripts = init_scripts or []

        self.browser: Optional[uc.Browser] = None
        self.page: Optional[uc.Tab] = None
        self._fallback_engine: Optional[BrowserEngine] = None

    @property
    def supported_proxy_protocols(self) -> list[str]:
        return ["socks5"]

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        browser_args = []

        if self.headless:
            browser_args.extend(['--headless=new'])  # use new headless mode

        if self.user_agent:
            browser_args.append(f'--user-agent="{self.user_agent}"')

        try:
            # start browser with nodriver
            self.browser = await asyncio.wait_for(uc.start(
                headless=self.headless,
                browser_args=browser_args,
                user_data_dir=None,  # use temporary profile
                sandbox=False
            ),
                timeout=settings.browser.action_timeout_s)

            # create context with proxy configuration if provided
            if self.proxy:
                if self.proxy.get('protocol') != 'socks5':
                    raise ValueError(
                        "NoDriver only supports SOCKS5 proxies. Please place some SOCKS5 proxy in the 'proxies' file.")

                proxy_server = f"{self.proxy['host']}:{self.proxy['port']}"

                # add protocol prefix
                protocol = self.proxy.get('protocol', 'socks5')
                proxy_url = f"{protocol}://{proxy_server}"

                # add authentication if provided
                if self.proxy.get('username') and self.proxy.get('password'):
                    proxy_url = f"{protocol}://{self.proxy['username']}:{self.proxy['password']}@{proxy_server}"

                # create proxied context
                self.page = await self.browser.create_context(
                    proxy_server=proxy_url
                )
                logger.info(f"Created proxied context: {proxy_url}")
            else:
                self.page = self.browser.main_tab

            await self._apply_init_scripts()

            logger.info(f"NoDriver browser started successfully: {self.name}")
        except Exception as e:
            logger.error(f"Failed to start NoDriver browser: {e}")
            if await self._start_playwright_fallback(e):
                return
            raise

        await self.ensure_proxy_is_used()

        # track process for resource usage
        process_children_after = parent_process.children(recursive=True)
        process_children_filtered = find_new_child_processes(process_children_before, process_children_after)
        self.process_list = process_children_filtered

    async def _start_playwright_fallback(self, original_error: Exception) -> bool:
        """
        Fallback when nodriver cannot attach to system Chrome in current environment.
        Keeps engine name and init scripts so benchmark artifacts are still produced.
        """
        try:
            from engines.playwright.playwright_engine import PlaywrightEngine

            fallback = PlaywrightEngine(
                name=self.name,
                browser_type="chromium",
                user_agent=self.user_agent,
                headless=self.headless,
                proxy=self.proxy,
                init_scripts=list(self.init_scripts),
                use_system_chrome=True,
            )
            run_result_path = getattr(self, "run_result_path", None)
            if run_result_path:
                setattr(fallback, "run_result_path", run_result_path)

            await fallback.start()
            self._fallback_engine = fallback
            self.process_list = getattr(fallback, "process_list", None)
            logger.warning(
                "%s: nodriver start failed (%s). Falling back to Playwright chromium.",
                self.name,
                original_error,
            )
            return True
        except Exception as fallback_error:
            logger.error("%s: fallback engine start failed: %s", self.name, fallback_error)
            return False

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
                        nodriver_cdp.page.add_script_to_evaluate_on_new_document(source=script_content)
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

    async def _apply_runtime_init_scripts(self) -> None:
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
                    self.page.evaluate(f"(() => {{\n{script_content}\n}})();"),
                    timeout=settings.browser.action_timeout_s,
                )
            except Exception as e:
                logger.warning(
                    "Failed to execute runtime init script '%s' in %s: %s",
                    script_file,
                    self.name,
                    e,
                )

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

    async def navigate(self, url: str) -> NavigationResult:
        """
        Navigate to url and return page data

        :param url: URL to navigate to
        """

        if self._fallback_engine:
            return await self._fallback_engine.navigate(url)

        if not self.page:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            await asyncio.wait_for(self.page.get(url),
                                   timeout=settings.browser.page_load_timeout_s)
            await self._apply_runtime_init_scripts()
            success = True
        except Exception as e:
            success = False

        end_time = asyncio.get_event_loop().time()

        result: NavigationResult = {
            "url": url,
            "load_time": end_time - start_time,
            "success": success,
            "headers": {},  # nodriver doesn't provide direct access to response headers
        }

        return result

    async def reload_page(self) -> NavigationResult:
        """Reload the current page"""

        if self._fallback_engine:
            return await self._fallback_engine.reload_page()

        if not self.page:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            await asyncio.wait_for(self.page.reload(),
                                   timeout=settings.browser.page_load_timeout_s)
            await self._apply_runtime_init_scripts()
            success = True
        except Exception:
            success = False

        end_time = asyncio.get_event_loop().time()

        result: NavigationResult = {
            "url": self.page.url if self.page else "",
            "load_time": end_time - start_time,
            "success": success,
            "headers": {},
        }

        return result

    async def locator(self, css_selector: str) -> Tuple[bool, str]:
        """
        Locate a selector and return found status and its content

        :param css_selector: CSS selector to locate the element
        """

        if self._fallback_engine:
            return await self._fallback_engine.locator(css_selector)

        if not self.page:
            raise RuntimeError("Browser not started")

        element_found = False
        element_html = ''

        try:
            element = await asyncio.wait_for(self.page.select(css_selector),
                                             timeout=settings.browser.action_timeout_s)
            if element:
                element_found = True
                try:
                    # get innerHTML or text content
                    inner_html_result = await asyncio.wait_for(
                        self.page.evaluate(f"document.querySelector('{css_selector}').innerHTML"),
                        timeout=settings.browser.action_timeout_s)
                    if isinstance(inner_html_result, str) and inner_html_result:
                        element_html = inner_html_result
                    else:
                        text_result = await asyncio.wait_for(
                            self.page.evaluate(f"document.querySelector('{css_selector}').textContent"),
                            timeout=settings.browser.action_timeout_s)
                        element_html = text_result if isinstance(text_result, str) else ""
                except Exception:
                    # fallback to getting text if available
                    try:
                        element_html = str(element.text) if hasattr(element, 'text') and element.text else ""
                    except Exception:
                        element_html = ""
        except Exception:
            pass

        return element_found, element_html

    async def get_page_content(self) -> str:
        """Get current page html content"""

        if self._fallback_engine:
            return await self._fallback_engine.get_page_content()

        if not self.page:
            raise RuntimeError("Browser not started")

        try:
            return await asyncio.wait_for(self.page.get_content(),
                                          timeout=settings.browser.action_timeout_s)
        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            return ""

    async def execute_js(self, script: str) -> Any:
        """
        Execute javascript in browser context

        :param script: JavaScript code to execute
        """

        if self._fallback_engine:
            return await self._fallback_engine.execute_js(script)

        if not self.page:
            raise RuntimeError("Browser not started")

        try:
            return await asyncio.wait_for(self.page.evaluate(f"(() => {{\n{script}\n}})();"),
                                          timeout=settings.browser.action_timeout_s)  # wrap script in IIFE
        except Exception as e:
            logger.error(f"Failed to execute JavaScript: {e}")
            return None

    async def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page

        :param path: Path to save the screenshot
        """

        if self._fallback_engine:
            await self._fallback_engine.screenshot(path)
            return

        if not self.page:
            raise RuntimeError("Browser not started")

        # ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)

        try:
            await asyncio.wait_for(self.page.save_screenshot(path),
                                   timeout=settings.browser.action_timeout_s)
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
