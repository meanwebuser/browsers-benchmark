#!/usr/bin/env python3
import asyncio
import os
from typing import Any

import pytest

from config.engines import engines_config

pytestmark = pytest.mark.engine

EXAMPLE_URL = "https://example.com/"


def _selected_engine_configs() -> list[dict[str, Any]]:
    all_configs = list(engines_config.engines)
    requested_raw = os.environ.get("ENGINE_SMOKE_ENGINES", "").strip()
    if not requested_raw:
        return all_configs

    requested_names = {name.strip() for name in requested_raw.split(",") if name.strip()}
    if not requested_names:
        return all_configs

    selected = [cfg for cfg in all_configs if cfg.get("params", {}).get("name") in requested_names]
    found_names = {cfg.get("params", {}).get("name") for cfg in selected}
    missing = sorted(requested_names - found_names)
    if missing:
        raise ValueError(f"ENGINE_SMOKE_ENGINES contains unknown names: {', '.join(missing)}")
    return selected


def _engine_id(engine_config: dict[str, Any]) -> str:
    params = engine_config.get("params", {})
    return str(params.get("name", engine_config.get("class").__name__))


ENGINE_CONFIGS = _selected_engine_configs()


async def _run_engine_base_api_smoke(engine_config: dict[str, Any]) -> None:
    engine_cls = engine_config["class"]
    params = dict(engine_config.get("params", {}))
    engine_name = str(params.get("name", engine_cls.__name__))
    engine = engine_cls(**params)

    try:
        await engine.start()

        nav = await engine.navigate(EXAMPLE_URL)
        assert bool(nav.get("success", False)), f"{engine_name}: navigate() failed"
        assert isinstance(nav.get("url", ""), str), f"{engine_name}: navigate() returned invalid url"

        found, html = await engine.locator("h1")
        assert found, f"{engine_name}: locator('h1') did not find element on example.com"
        assert isinstance(html, str) and html.strip(), f"{engine_name}: locator('h1') returned empty html"

        js_result = await engine.execute_js("return window.location.hostname;")
        assert isinstance(js_result, str), f"{engine_name}: execute_js() did not return str hostname"
        assert "example" in js_result.lower(), f"{engine_name}: unexpected hostname from execute_js(): {js_result!r}"

        page_content = await engine.get_page_content()
        assert isinstance(page_content, str) and page_content.strip(), f"{engine_name}: get_page_content() is empty"
        assert "example" in page_content.lower(), f"{engine_name}: get_page_content() does not look like example.com"

        reload_result = await engine.reload_page()
        assert isinstance(reload_result, dict), f"{engine_name}: reload_page() did not return a dict"
        assert isinstance(reload_result.get("url", ""), str), f"{engine_name}: reload_page() returned invalid url"
    finally:
        await engine.stop()
        # Give subprocess trees a short grace period to exit fully.
        await asyncio.sleep(0.2)

        live_processes = engine._get_live_processes()
        assert not live_processes, f"{engine_name}: stop() left live processes: {[p.pid for p in live_processes]}"
        assert engine.get_memory_usage() == 0, f"{engine_name}: memory usage after stop is not zero"


@pytest.mark.skipif(os.environ.get("RUN_ENGINE_TESTS") != "1", reason="Set RUN_ENGINE_TESTS=1 to run engine diagnostics")
@pytest.mark.parametrize("engine_config", ENGINE_CONFIGS, ids=_engine_id)
def test_all_declared_engines_base_api(engine_config: dict[str, Any]) -> None:
    asyncio.run(_run_engine_base_api_smoke(engine_config))
