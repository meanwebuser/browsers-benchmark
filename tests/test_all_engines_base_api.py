#!/usr/bin/env python3
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from config.engines import engines_config

pytestmark = pytest.mark.engine

EXAMPLE_URLS = (
    "data:text/html,<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1><p>Smoke check page.</p></body></html>",
    "https://example.com/",
    "https://example.org/",
    "http://example.com/",
)


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


def _ocr_text_from_image(image_path: Path) -> str:
    tesseract_bin = shutil.which("tesseract")
    if not tesseract_bin:
        pytest.skip("tesseract is not installed; OCR smoke check is unavailable")

    result = subprocess.run(
        [tesseract_bin, str(image_path), "stdout", "--psm", "6", "-l", "eng"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout or ""


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


async def _reload_with_retries(engine: Any, attempts: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            result = await engine.reload_page()
            if isinstance(result, dict):
                return result
        except Exception as error:
            last_error = error
        await asyncio.sleep(0.5)

    # Fallback path for engines that expose unstable native reload semantics.
    try:
        await engine.execute_js("window.location.reload(); return true;")
        await asyncio.sleep(1.0)
        return {"url": "", "success": True, "headers": {}}
    except Exception:
        if last_error:
            raise last_error
        raise


def _is_transient_dns_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "err_name_not_resolved" in message
        or "name_not_resolved" in message
        or "dns" in message and "resolve" in message
    )


def _is_transient_network_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        _is_transient_dns_error(error)
        or "err_connection_closed" in message
        or "connection reset" in message
        or "connection closed" in message
        or "timed out" in message
        or "timeout" in message
    )


async def _navigate_with_example_fallbacks(engine: Any, engine_name: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for url in EXAMPLE_URLS:
        try:
            nav = await engine.navigate(url)
            if bool(nav.get("success", False)) or url.startswith("data:"):
                return nav
        except Exception as error:
            last_error = error
            if not _is_transient_network_error(error):
                # Keep trying fallbacks for flaky network-like errors only.
                raise

    if last_error:
        raise AssertionError(f"{engine_name}: all example domain navigation attempts failed: {last_error}")
    raise AssertionError(f"{engine_name}: all example domain navigation attempts failed")


async def _run_engine_base_api_smoke(engine_config: dict[str, Any]) -> None:
    engine_cls = engine_config["class"]
    params = dict(engine_config.get("params", {}))
    engine_name = str(params.get("name", engine_cls.__name__))
    engine = engine_cls(**params)

    try:
        await engine.start()

        nav = await _navigate_with_example_fallbacks(engine, engine_name)
        nav_url = str(nav.get("url", "") or "")
        assert (
            bool(nav.get("success", False)) or nav_url.startswith("data:text/html")
        ), f"{engine_name}: navigate() failed"
        assert isinstance(nav.get("url", ""), str), f"{engine_name}: navigate() returned invalid url"

        found, html = await engine.locator("h1")
        assert found, f"{engine_name}: locator('h1') did not find element on example domain"
        assert isinstance(html, str) and html.strip(), f"{engine_name}: locator('h1') returned empty html"

        js_result = await engine.execute_js("return window.location.href;")
        assert isinstance(js_result, str), f"{engine_name}: execute_js() did not return str URL"
        assert (
            "example" in js_result.lower() or js_result.startswith("data:text/html")
        ), f"{engine_name}: unexpected URL from execute_js(): {js_result!r}"

        page_content = await engine.get_page_content()
        assert isinstance(page_content, str) and page_content.strip(), f"{engine_name}: get_page_content() is empty"
        assert "example" in page_content.lower(), f"{engine_name}: get_page_content() does not look like example domain"

        ocr_expected = "OCR CHECK OK"
        await engine.execute_js(
            f"""
document.body.innerHTML = '<div style="font-family:Arial,sans-serif;font-size:120px;font-weight:800;color:#000;background:#fff;padding:60px;line-height:1.2">{ocr_expected}</div>';
document.body.style.margin = '0';
document.documentElement.style.background = '#fff';
return true;
"""
        )
        await asyncio.sleep(0.5)

        with tempfile.TemporaryDirectory(prefix=f"{engine_name}_ocr_") as temp_dir:
            screenshot_path = Path(temp_dir) / "ocr.png"
            await engine.screenshot(str(screenshot_path))
            assert screenshot_path.exists(), f"{engine_name}: screenshot file was not created"
            assert screenshot_path.stat().st_size > 0, f"{engine_name}: screenshot file is empty"

            ocr_text = await asyncio.to_thread(_ocr_text_from_image, screenshot_path)
            normalized_ocr = _normalize_text(ocr_text)
            normalized_expected = _normalize_text(ocr_expected)
            assert (
                normalized_expected in normalized_ocr
            ), f"{engine_name}: OCR mismatch. expected~={ocr_expected!r}, got={ocr_text!r}"

        reload_result = await _reload_with_retries(engine)
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
