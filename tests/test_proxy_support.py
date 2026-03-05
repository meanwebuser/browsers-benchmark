import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.engines import engines_config
from engines.playwright.cloakbrowser_engine import CloakBrowserEngine


async def _run_cloakbrowser_proxy_start_check(proxy: dict[str, Any]) -> AsyncMock:
    launch_mock = AsyncMock()
    browser = AsyncMock()
    context = AsyncMock()
    page = AsyncMock()

    launch_mock.return_value = browser
    browser.new_context.return_value = context
    context.new_page.return_value = page
    page.set_default_timeout = MagicMock()
    page.set_default_navigation_timeout = MagicMock()

    engine = CloakBrowserEngine(name="cloakbrowser-test", proxy=proxy)
    engine.ensure_proxy_is_used = AsyncMock()

    import engines.playwright.cloakbrowser_engine as cloakbrowser_module

    original_launch = cloakbrowser_module.launch_async
    cloakbrowser_module.launch_async = launch_mock
    try:
        await engine.start()
        await engine.stop()
    finally:
        cloakbrowser_module.launch_async = original_launch

    return launch_mock


def test_cloakbrowser_launch_uses_proxy_url_string() -> None:
    proxy = {
        "protocol": "http",
        "host": "proxy.example.com",
        "port": "8080",
        "username": "user@example.com",
        "password": "pa:ss@word",
    }

    launch_mock = asyncio.run(_run_cloakbrowser_proxy_start_check(proxy))
    assert launch_mock.await_count == 1
    proxy_value = launch_mock.await_args.kwargs.get("proxy")
    assert isinstance(proxy_value, str)
    assert proxy_value == "http://user%40example.com:pa%3Ass%40word@proxy.example.com:8080"


def test_all_configured_engines_declare_proxy_support() -> None:
    failing: list[str] = []

    for engine_config in engines_config.engines:
        engine_cls = engine_config["class"]
        params = dict(engine_config.get("params", {}))
        engine_name = str(params.get("name", engine_cls.__name__))
        engine = engine_cls(**params)
        protocols = getattr(engine, "supported_proxy_protocols", None)
        if not isinstance(protocols, list) or not protocols:
            failing.append(f"{engine_name}: missing supported_proxy_protocols")
            continue
        if not all(isinstance(p, str) and p.strip() for p in protocols):
            failing.append(f"{engine_name}: invalid protocols={protocols!r}")

    assert not failing, "Engines without declared proxy support:\n" + "\n".join(failing)
