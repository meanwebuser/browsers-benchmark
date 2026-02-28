import abc
import ipaddress
import json
import logging
import re
import time
from typing import Dict, Optional, Any, TypedDict, Tuple, List

import psutil

logger = logging.getLogger(__name__)


class NavigationResult(TypedDict):
    """
    Result of a navigation operation

    :param url: URL of the page after navigation
    :param load_time: Time taken to load the page in seconds
    :param success: Whether the navigation was successful
    :param headers: Response headers from the navigation request (not always available)
    """

    url: str
    load_time: float
    success: bool
    headers: Dict[str, str]


class BrowserEngine(abc.ABC):
    """
    Base class for all browser engine implementations

    :param name: Name of the browser engine.

    :param proxy: Optional proxy settings for the browser.
    :param proxy['protocol']: Proxy protocol (e.g., 'http', 'socks5').
    :param proxy['host']: Proxy host.
    :param proxy['port']: Proxy port.
    :param proxy['username']: Optional proxy username.
    :param proxy['password']: Optional proxy password.
    """

    def __init__(self, name: str, proxy: Optional[Dict[str, str]] = None):
        self.name = name
        self.proxy = proxy
        self.known_direct_external_ip: Optional[str] = None
        self.process_list = []
        self.browser = None
        self._start_time = None

    @property
    @abc.abstractmethod
    def supported_proxy_protocols(self) -> list[str]:
        """List of supported proxy protocols for this engine"""
        pass

    @abc.abstractmethod
    async def start(self) -> None:
        """Initialize and start the browser"""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the browser and clean up resources"""
        pass

    async def restart(self) -> None:
        """Recreate and restart the browser engine"""

        await self.stop()
        await self.start()

    @abc.abstractmethod
    async def navigate(self, url: str) -> NavigationResult:
        """
        Navigate to url and return page data

        :param url: URL to navigate to
        """

        pass

    @abc.abstractmethod
    async def reload_page(self) -> NavigationResult:
        """Reload the current page"""
        pass

    @abc.abstractmethod
    async def locator(self, css_selector: str) -> Tuple[bool, str]:
        """
        Locate a selector and return its content

        :param css_selector: CSS selector to locate element
        """

        pass

    @abc.abstractmethod
    async def get_page_content(self) -> str:
        """Get current page html content"""
        pass

    @abc.abstractmethod
    async def execute_js(self, script: str) -> Any:
        """
        Execute javascript in browser context

        :param script: JavaScript code to execute
        """

        pass

    @abc.abstractmethod
    async def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page

        :param path: Path to save the screenshot
        """

        pass

    def get_memory_usage(self) -> int:
        """Get current memory usage in MB"""

        live_processes = self._get_live_processes()
        if not live_processes:
            return 0

        total_memory = 0
        for proc in live_processes:
            try:
                memory_info = proc.memory_info()
                total_memory += memory_info.rss  # Resident Set Size in bytes
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return total_memory // (1024 * 1024)  # convert to MB

    def get_cpu_usage(self) -> float:
        """Get current cpu usage percentage"""

        live_processes = self._get_live_processes()
        if not live_processes:
            return 0.0

        # Prime counters for a consistent sample window.
        for proc in live_processes:
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        time.sleep(0.1)

        total_cpu = 0.0
        for proc in live_processes:
            try:
                total_cpu += proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return total_cpu

    def _get_live_processes(self) -> List[psutil.Process]:
        """
        Build current process list from tracked roots and all their descendants.
        This keeps resource accounting valid even when browser spawns extra workers later.
        """
        if not self.process_list:
            return []

        processes_by_pid: Dict[int, psutil.Process] = {}

        for root_proc in self.process_list:
            try:
                if not root_proc.is_running():
                    continue
                processes_by_pid[root_proc.pid] = root_proc
                for child in root_proc.children(recursive=True):
                    if child.is_running():
                        processes_by_pid[child.pid] = child
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return list(processes_by_pid.values())

    def get_runtime(self) -> float:
        """Get runtime in seconds since browser start"""

        if not self._start_time:
            return 0.0
        return time.time() - self._start_time

    @staticmethod
    def _extract_ip(raw_text: str) -> Optional[str]:
        if not raw_text:
            return None

        raw_text = raw_text.strip()
        if not raw_text:
            return None

        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                value = parsed.get("ip")
                if isinstance(value, str):
                    ipaddress.ip_address(value.strip())
                    return value.strip()
        except Exception:
            pass

        for candidate in re.findall(r"[0-9a-fA-F:.]+", raw_text):
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except Exception:
                continue

        return None

    async def get_browser_external_ip(self) -> Optional[str]:
        """Get external IP from inside browser context via ipify."""
        ipify_url = "https://api.ipify.org?format=json"
        await self.navigate(ipify_url)

        element_found, element_html = await self.locator("pre")
        if element_found and element_html:
            ip = self._extract_ip(element_html)
            if ip:
                return ip

        page_content = await self.get_page_content()
        return self._extract_ip(page_content)

    async def ensure_proxy_is_used(self) -> None:
        """Validate that configured proxy is actually used by the browser."""
        from config.settings import settings

        if not self.proxy or not settings.proxy.debug_verify_usage:
            return

        from utils.proxy.proxy_manager import get_external_ip

        direct_ip = self.known_direct_external_ip or get_external_ip(timeout=settings.proxy.test_timeout)
        browser_ip = await self.get_browser_external_ip()

        if not browser_ip:
            raise RuntimeError(f"{self.name}: proxy check failed - browser IP is empty")

        if direct_ip and browser_ip == direct_ip:
            raise RuntimeError(
                f"{self.name}: proxy check failed - browser IP ({browser_ip}) equals direct IP ({direct_ip})"
            )

        if direct_ip:
            logger.info("%s proxy check passed: direct IP %s -> browser IP %s", self.name, direct_ip, browser_ip)
        else:
            logger.warning(
                "%s proxy check passed with browser IP %s, but direct IP is unavailable",
                self.name,
                browser_ip
            )
