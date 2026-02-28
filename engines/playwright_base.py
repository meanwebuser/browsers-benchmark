import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from typing import Dict, Optional, Any, Tuple, Literal, List

import psutil
from playwright.async_api import async_playwright, BrowserType, Locator

from config.settings import settings
from engines.base import BrowserEngine
from utils.js_script import load_js_script
from utils.process import find_new_child_processes

logger = logging.getLogger(__name__)


class PlaywrightBase(BrowserEngine):
    def __init__(
            self,
            name: str = "playwright-chrome",
            browser_type: Literal['chromium', 'firefox', 'webkit'] = "chromium",

            user_agent: Optional[str] = None,
            headless: bool = True,
            proxy: Optional[Dict[str, str]] = None,
            init_scripts: Optional[List[str]] = None,
            use_system_chrome: bool = False,
            connect_over_cdp: bool = False,
            cdp_host: str = "127.0.0.1",
            cdp_port: int = 0,
            **kwargs
    ):
        """
        Initialize the PlaywrightBase with the given parameters

        :param name: Name of the engine instance
        :param browser_type: Type of browser to use (chromium, firefox, webkit)
        :param user_agent: Custom user agent string
        :param headless: Whether to run the browser in headless
        :param proxy: Proxy settings, if any
        """

        super().__init__(name, proxy)
        self.browser_type = browser_type  # chromium, firefox, webkit
        self.headless = headless
        self.user_agent = user_agent
        self.init_scripts = init_scripts or []
        self.use_system_chrome = use_system_chrome
        self.connect_over_cdp = connect_over_cdp
        self.cdp_host = cdp_host
        self.cdp_port = cdp_port

        self.playwright = None
        self.context = None
        self.page = None
        self._cdp_chrome_process: Optional[subprocess.Popen] = None
        self._cdp_user_data_dir: Optional[str] = None
        self._xvfb_process: Optional[subprocess.Popen] = None
        self._xvfb_display: Optional[str] = None

    @property
    def supported_proxy_protocols(self) -> list[str]:
        return ["http", "https"]

    def _has_display_server(self) -> bool:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def _ensure_virtual_display(self) -> bool:
        if self._has_display_server():
            return True

        if self._xvfb_process and self._xvfb_process.poll() is None and self._xvfb_display:
            os.environ["DISPLAY"] = self._xvfb_display
            return True

        xvfb_bin = shutil.which("Xvfb")
        if not xvfb_bin:
            logger.warning("%s requested headed mode, but Xvfb is not installed.", self.name)
            return False

        for display_num in range(99, 120):
            display = f":{display_num}"
            socket_path = f"/tmp/.X11-unix/X{display_num}"
            if os.path.exists(socket_path):
                continue

            try:
                process = subprocess.Popen(
                    [xvfb_bin, display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(0.2)
                if process.poll() is None:
                    self._xvfb_process = process
                    self._xvfb_display = display
                    os.environ["DISPLAY"] = display
                    logger.warning(
                        "%s requested headed mode without display server. Started Xvfb on %s.",
                        self.name,
                        display
                    )
                    return True
            except Exception as e:
                logger.warning("Failed to start Xvfb on %s: %s", display, e)

        logger.warning("%s could not start Xvfb for headed mode.", self.name)
        return False

    def _stop_virtual_display(self) -> None:
        if not self._xvfb_process:
            return

        try:
            if self._xvfb_process.poll() is None:
                self._xvfb_process.terminate()
                self._xvfb_process.wait(timeout=2)
        except Exception:
            try:
                self._xvfb_process.kill()
            except Exception:
                pass
        finally:
            self._xvfb_process = None
            self._xvfb_display = None

    def get_effective_headless(self) -> bool:
        """
        Resolve runtime headless mode.
        Try Xvfb for headed mode in environments without a display server.
        """

        if self.headless:
            return True

        if not self._has_display_server() and not self._ensure_virtual_display():
            raise RuntimeError(
                f"{self.name} requested headed mode, but no display server is available and Xvfb "
                f"is not installed or failed to start."
            )

        return False

    @staticmethod
    def _is_missing_display_error(exc: Exception) -> bool:
        """
        Detect Playwright launch failures caused by missing/invalid display server.
        """
        msg = str(exc).lower()
        return (
            "xserver" in msg
            or "headed browser without having a xserver running" in msg
            or "missing x server" in msg
            or "wayland" in msg and "display" in msg
        )

    def _resolve_system_chrome_binary(self) -> str:
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chrome",
            "chromium-browser",
            "chromium",
        ]
        for candidate in candidates:
            binary = shutil.which(candidate)
            if binary:
                return binary

        raise RuntimeError(
            f"{self.name}: system Chrome binary not found. "
            f"Checked: {', '.join(candidates)}"
        )

    def _build_proxy_server(self) -> Optional[str]:
        if not self.proxy:
            return None
        return f"{self.proxy['protocol']}://{self.proxy['host']}:{self.proxy['port']}"

    def _pick_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((self.cdp_host, 0))
            return sock.getsockname()[1]

    def _ensure_local_no_proxy(self) -> None:
        hosts = {"localhost", "127.0.0.1", self.cdp_host}
        current_no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        current_hosts = {h.strip() for h in current_no_proxy.split(",") if h.strip()}
        merged_hosts = sorted(current_hosts | hosts)
        merged_value = ",".join(merged_hosts)
        os.environ["NO_PROXY"] = merged_value
        os.environ["no_proxy"] = merged_value

    def _fetch_cdp_ws_endpoint(self, cdp_url: str) -> str:
        request_url = f"{cdp_url}/json/version"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request_url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        ws_endpoint = payload.get("webSocketDebuggerUrl")
        if not ws_endpoint:
            raise RuntimeError(f"CDP endpoint did not return webSocketDebuggerUrl: {request_url}")
        return ws_endpoint

    async def _start_and_connect_over_cdp(self, effective_headless: bool) -> None:
        if self.browser_type != "chromium":
            raise ValueError("connect_over_cdp is only supported for chromium")

        chrome_binary = self._resolve_system_chrome_binary()
        self._cdp_user_data_dir = tempfile.mkdtemp(prefix=f"{self.name}-cdp-profile-")

        cdp_port = self.cdp_port if self.cdp_port > 0 else self._pick_free_port()

        chrome_args = [
            chrome_binary,
            f"--remote-debugging-port={cdp_port}",
            f"--remote-debugging-address={self.cdp_host}",
            f"--user-data-dir={self._cdp_user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]

        proxy_server = self._build_proxy_server()
        if proxy_server:
            chrome_args.append(f"--proxy-server={proxy_server}")
            if self.proxy and self.proxy.get("username") and self.proxy.get("password"):
                logger.warning(
                    "%s: proxy auth credentials are not applied in connect_over_cdp mode.",
                    self.name,
                )

        if effective_headless:
            chrome_args.extend(["--headless=new", "--disable-gpu"])

        self._cdp_chrome_process = subprocess.Popen(
            chrome_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        cdp_url = f"http://{self.cdp_host}:{cdp_port}"
        self._ensure_local_no_proxy()
        last_error = None
        for _ in range(30):
            if self._cdp_chrome_process.poll() is not None:
                raise RuntimeError(f"{self.name}: system Chrome exited before CDP became available")

            try:
                ws_endpoint = self._fetch_cdp_ws_endpoint(cdp_url)
                self.browser = await self.playwright.chromium.connect_over_cdp(ws_endpoint)
                break
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.2)
        else:
            raise RuntimeError(f"{self.name}: failed to connect over CDP to {cdp_url}: {last_error}")

        self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        if self.user_agent:
            logger.warning(
                "%s: custom user_agent is not applied in connect_over_cdp mode (existing context is reused).",
                self.name,
            )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    def _stop_cdp_chrome_process(self) -> None:
        if self._cdp_chrome_process:
            try:
                if self._cdp_chrome_process.poll() is None:
                    self._cdp_chrome_process.terminate()
                    self._cdp_chrome_process.wait(timeout=3)
            except Exception:
                try:
                    self._cdp_chrome_process.kill()
                except Exception:
                    pass
            finally:
                self._cdp_chrome_process = None

        if self._cdp_user_data_dir:
            shutil.rmtree(self._cdp_user_data_dir, ignore_errors=True)
            self._cdp_user_data_dir = None

    async def start(self) -> None:
        """Initialize and start the browser"""

        self._start_time = asyncio.get_event_loop().time()

        # get processes before browser is started
        parent_process = psutil.Process(os.getpid())
        process_children_before = parent_process.children(recursive=True)

        # initialize playwright
        self.playwright = await async_playwright().start()

        # launch browser type
        if self.browser_type not in ["chromium", "firefox", "webkit"]:
            raise ValueError(f"unsupported browser type: {self.browser_type}")

        browser_launcher: BrowserType = getattr(self.playwright, self.browser_type)
        effective_headless = self.get_effective_headless()
        if self.connect_over_cdp:
            await self._start_and_connect_over_cdp(effective_headless)
        else:
            launch_options: Dict[str, Any] = {"headless": effective_headless}
            if self.browser_type == "chromium" and self.use_system_chrome:
                launch_options["channel"] = "chrome"

            try:
                self.browser = await browser_launcher.launch(**launch_options)
            except Exception as e:
                if not effective_headless and self._is_missing_display_error(e):
                    logger.warning(
                        "%s failed to start in headed mode due to display issue; retrying in headless mode.",
                        self.name
                    )
                    launch_options["headless"] = True
                    self.browser = await browser_launcher.launch(**launch_options)
                else:
                    raise

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
            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()

        self.page.set_default_timeout(settings.browser.action_timeout_s * 1000)
        self.page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)

        # monkey-patch attachShadow to force open mode for closed shadow DOM
        await self.context.add_init_script(await load_js_script('unlockShadowDom.js'))
        for script_file in self.init_scripts:
            await self.context.add_init_script(
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
            if self.playwright:
                await self.playwright.stop()
        except:
            pass
        self.playwright = None

        self._stop_cdp_chrome_process()
        self._stop_virtual_display()
        self.process_list = None

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to url and return page data"""

        if not self.page:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()
        response = await self.page.goto(url, timeout=settings.browser.page_load_timeout_s * 1000)
        end_time = asyncio.get_event_loop().time()

        result = {
            "url": url,
            "load_time": end_time - start_time,
            "success": response.ok if response else False,
            "headers": response.headers if response else {},
        }

        return result

    async def reload_page(self):
        """Reload the current page"""

        if not self.page:
            raise RuntimeError("Browser not started")

        start_time = asyncio.get_event_loop().time()
        response = await self.page.reload(timeout=settings.browser.page_load_timeout_s * 1000)
        end_time = asyncio.get_event_loop().time()

        result = {
            "url": self.page.url,
            "load_time": end_time - start_time,
            "success": response.ok if response else False,
            "headers": response.headers if response else {},
        }

        return result

    async def locator(self, selector: str) -> Tuple[bool, str]:
        """
        Locate a selector and return found status and its content

        :param selector: CSS selector to locate
        """

        if not self.page:
            raise RuntimeError("browser not started")

        element_found = False
        element_html = ''

        element: Locator = self.page.locator(selector)
        if await element.count() > 0:
            element_found = True
            element_html: str = await element.inner_html(timeout=settings.browser.action_timeout_s * 1000)

        return element_found, element_html

    async def get_page_content(self) -> str:
        """Get current page html content"""

        if not self.page:
            raise RuntimeError("browser not started")

        return await self.page.content()

    async def execute_js(self, script: str) -> Any:
        """
        Execute javascript in browser context

        :param script: JavaScript code to execute
        """

        if not self.page:
            raise RuntimeError("browser not started")

        return await self.page.evaluate(
            f"(() => {{\n{script}\n}})();")  # wrap script in IIFE

    async def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page

        :param path: Path to save the screenshot
        """

        if not self.page:
            raise RuntimeError("browser not started")

        await self.page.screenshot(path=path)
