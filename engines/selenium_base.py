import asyncio
import logging
import os
from typing import Dict, Optional, Any, Tuple, Union, List

import psutil
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait

from config.settings import settings
from engines.base import BrowserEngine, NavigationResult
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)

"""
This Selenium Browser Engine implementation doesn't support proxies with auth.
It is possible to add it, but that requires a lot of additional setup and I think no one even needs it 
since Selenium is deprecated. It is easier to do with selenium-wire, which is also deprecated.
"""


class SeleniumBase(BrowserEngine):
    def __init__(
            self,
            name: str = "selenium-chrome",
            browser_type: str = "chrome",

            user_agent: Optional[str] = None,
            headless: bool = True,

            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        """
        Initialize the SeleniumBase with the given parameters

        :param name: Name of the engine instance
        :param browser_type: Type of browser to use (chrome, firefox, edge)
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        super().__init__(name, proxy)
        self.browser_type = browser_type  # chrome, firefox
        self.headless = headless
        self.user_agent = user_agent
        self.init_scripts = init_scripts or []

        self.driver = None
        self.wait = None

    @staticmethod
    def _ensure_local_no_proxy() -> None:
        """Ensure localhost WebDriver traffic does not go through outbound proxy."""
        hosts = {"localhost", "127.0.0.1", "::1"}
        current_no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        current_hosts = {h.strip() for h in current_no_proxy.split(",") if h.strip()}
        merged_hosts = sorted(current_hosts | hosts)
        merged_value = ",".join(merged_hosts)
        os.environ["NO_PROXY"] = merged_value
        os.environ["no_proxy"] = merged_value

    @property
    def supported_proxy_protocols(self) -> list[str]:
        """Selenium doesn't support proxies with auth, so we consider it as no proxy protocols because no one uses it anyway"""
        return ['http','socks5']

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        # configure browser options
        options = self._get_browser_options()

        if self.headless:
            options.add_argument("--headless")

        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")

        # add common arguments for better stealthiness
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        if self.proxy:
            proxy_url = self.proxy.get("url") if isinstance(self.proxy, dict) else str(self.proxy)
            if proxy_url:
                options.add_argument(f"--proxy-server={proxy_url}")

        # only add experimental options for chrome
        if self.browser_type.lower() == "chrome" and isinstance(options, ChromeOptions):
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

        # initialize driver
        self._ensure_local_no_proxy()
        self.driver = self._create_driver(options)

        # set up wait object for explicit waits
        self.wait = WebDriverWait(self.driver, timeout=settings.browser.page_load_timeout_s)

        # inject custom scripts before any page scripts execute (Chrome/Edge CDP)
        if self.init_scripts:
            if self.browser_type.lower() in {"chrome", "edge"}:
                for script_file in self.init_scripts:
                    script_content = await load_js_script(
                        script_file,
                        user_agent=self.user_agent,
                        browser_type=self.browser_type,
                    )
                    self.driver.execute_cdp_cmd(
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": script_content}
                    )
            else:
                logger.warning(
                    "Custom init scripts are only supported for Selenium Chrome/Edge via CDP. Skipping: %s",
                    self.init_scripts
                )

        # remove webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        await self.ensure_proxy_is_used()

        # track process for resource usage
        process_children_after = parent_process.children(recursive=True)
        process_children_filtered = find_new_child_processes(process_children_before, process_children_after)
        self.process_list = process_children_filtered

    def _get_browser_options(self) -> Union[ChromeOptions, FirefoxOptions, EdgeOptions]:
        """Get browser-specific options object"""

        if self.browser_type.lower() == "chrome":
            return ChromeOptions()
        elif self.browser_type.lower() == "firefox":
            return FirefoxOptions()
        elif self.browser_type.lower() == "edge":
            return EdgeOptions()
        else:
            raise ValueError(f"Unsupported browser type: {self.browser_type}")

    def _create_driver(self, options: Union[ChromeOptions, FirefoxOptions, EdgeOptions]):
        """
        Create WebDriver instance based on browser type

        :param options: Browser options object
        """

        if self.browser_type.lower() == "chrome":
            return webdriver.Chrome(options=options)
        elif self.browser_type.lower() == "firefox":
            return webdriver.Firefox(options=options)
        elif self.browser_type.lower() == "edge":
            return webdriver.Edge(options=options)
        else:
            raise ValueError(f"Unsupported browser type: {self.browser_type}")

    async def stop(self) -> None:
        """Stop the browser and clean up resources"""

        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self.wait = None
        self.process_list = None

    async def navigate(self, url: str) -> NavigationResult:
        """
        Navigate to url and return page data

        :param url: URL to navigate to
        """

        if not self.driver:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            self.driver.get(url)
            success = True
        except WebDriverException as e:
            success = False

        end_time = asyncio.get_event_loop().time()

        result: NavigationResult = {
            "url": url,
            "load_time": end_time - start_time,
            "success": success,
            "headers": {},  # selenium doesn't provide response headers
        }

        return result

    async def reload_page(self) -> NavigationResult:
        """Reload the current page"""

        if not self.driver:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            self.driver.refresh()
            success = True
        except WebDriverException:
            success = False

        end_time = asyncio.get_event_loop().time()

        result: NavigationResult = {
            "url": self.driver.current_url if self.driver else "",
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

        if not self.driver:
            raise RuntimeError("Browser not started")

        element_found = False
        element_html = ''

        try:
            element = self.driver.find_element(By.CSS_SELECTOR, css_selector)
            if element:
                element_found = True
                element_html = element.get_attribute('innerHTML') or element.text
        except Exception:
            pass

        return element_found, element_html

    async def get_page_content(self) -> str:
        """Get current page html content"""

        if not self.driver:
            raise RuntimeError("Browser not started")

        return self.driver.page_source

    async def execute_js(self, script: str) -> Any:
        """
        Execute javascript in browser context

        :param script: JavaScript code to execute
        """

        if not self.driver:
            raise RuntimeError("Browser not started")

        return self.driver.execute_script(script)

    async def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page

        :param path: Path to save the screenshot
        """

        if not self.driver:
            raise RuntimeError("Browser not started")

        # ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.driver.save_screenshot(path)
