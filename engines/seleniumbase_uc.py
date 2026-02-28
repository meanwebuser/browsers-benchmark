import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import psutil
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from seleniumbase import Driver

from config.settings import settings
from engines.base import BrowserEngine, NavigationResult
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)


class SeleniumBaseUCEngine(BrowserEngine):
    def __init__(
            self,
            name: str = "seleniumbase-uc-chrome_headless",
            headless: bool = True,
            user_agent: Optional[str] = None,
            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            **kwargs
    ):
        super().__init__(name, proxy)
        self.headless = headless
        self.user_agent = user_agent
        self.init_scripts = init_scripts or []
        self.driver = None

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
        return ["http", "https", "socks5"]

    def _build_proxy_str(self) -> Optional[str]:
        if not self.proxy:
            return None

        protocol = self.proxy.get("protocol", "http")
        if protocol not in self.supported_proxy_protocols:
            raise ValueError(
                f"Unsupported proxy protocol: {protocol}. SeleniumBase UC supports: {self.supported_proxy_protocols}"
            )

        host = self.proxy.get("host")
        port = self.proxy.get("port")
        username = self.proxy.get("username")
        password = self.proxy.get("password")

        if not host or not port:
            raise ValueError("Proxy host and port are required when proxy is configured.")

        if username and password:
            return f"{protocol}://{username}:{password}@{host}:{port}"
        return f"{protocol}://{host}:{port}"

    async def start(self) -> None:
        self._start_time = asyncio.get_event_loop().time()

        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        driver_kwargs = {
            "uc": True,
            "headless": self.headless,
        }

        if self.user_agent:
            driver_kwargs["agent"] = self.user_agent

        proxy_str = self._build_proxy_str()
        if proxy_str:
            driver_kwargs["proxy"] = proxy_str

        self._ensure_local_no_proxy()
        self.driver = Driver(**driver_kwargs)
        self.driver.set_page_load_timeout(settings.browser.page_load_timeout_s)

        if self.init_scripts:
            for script_file in self.init_scripts:
                script_content = await load_js_script(
                    script_file,
                    user_agent=self.user_agent,
                    browser_type="chrome",
                )
                try:
                    self.driver.execute_cdp_cmd(
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": script_content}
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to register init script '%s' in SeleniumBase UC: %s",
                        script_file,
                        e
                    )

        await self.ensure_proxy_is_used()

        process_children_after = parent_process.children(recursive=True)
        self.process_list = find_new_child_processes(process_children_before, process_children_after)

    async def stop(self) -> None:
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

        self.driver = None
        self.process_list = None

    async def navigate(self, url: str) -> NavigationResult:
        if not self.driver:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            self.driver.get(url)
            success = True
        except WebDriverException:
            success = False

        end_time = asyncio.get_event_loop().time()

        return {
            "url": url,
            "load_time": end_time - start_time,
            "success": success,
            "headers": {},
        }

    async def reload_page(self) -> NavigationResult:
        if not self.driver:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()

        try:
            self.driver.refresh()
            success = True
        except WebDriverException:
            success = False

        end_time = asyncio.get_event_loop().time()

        return {
            "url": self.driver.current_url if self.driver else "",
            "load_time": end_time - start_time,
            "success": success,
            "headers": {},
        }

    async def locator(self, css_selector: str) -> Tuple[bool, str]:
        if not self.driver:
            raise RuntimeError("Browser not started")

        try:
            element = self.driver.find_element(By.CSS_SELECTOR, css_selector)
            if element:
                return True, element.get_attribute("innerHTML") or element.text or ""
        except Exception:
            pass

        return False, ""

    async def get_page_content(self) -> str:
        if not self.driver:
            raise RuntimeError("Browser not started")

        return self.driver.page_source

    async def execute_js(self, script: str) -> Any:
        if not self.driver:
            raise RuntimeError("Browser not started")

        return self.driver.execute_script(script)

    async def screenshot(self, path: str) -> None:
        if not self.driver:
            raise RuntimeError("Browser not started")

        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.driver.save_screenshot(path)
