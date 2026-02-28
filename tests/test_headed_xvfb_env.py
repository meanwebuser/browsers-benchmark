#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.engines import engines_config

pytestmark = pytest.mark.engine

DATA_URL = "data:text/html,<html><body>engine smoke</body></html>"
DISPLAY_ENV_KEYS = ("DISPLAY", "WAYLAND_DISPLAY", "MIR_SOCKET")


@dataclass
class CheckResult:
    engine_name: str
    status: str  # OK | FAIL | SKIP
    message: str


def _clear_display_env() -> dict[str, str | None]:
    previous = {}
    for key in DISPLAY_ENV_KEYS:
        previous[key] = os.environ.get(key)
        os.environ.pop(key, None)
    return previous


def _restore_display_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _filter_engine_configs(requested_names: list[str] | None) -> list[dict[str, Any]]:
    all_configs = list(engines_config.engines)
    if not requested_names:
        return all_configs

    requested_set = set(requested_names)
    filtered = [cfg for cfg in all_configs if cfg.get("params", {}).get("name") in requested_set]
    found = {cfg.get("params", {}).get("name") for cfg in filtered}
    missing = sorted(requested_set - found)
    if missing:
        raise ValueError(f"Unknown engine names: {', '.join(missing)}")
    return filtered


def _pick_engine_name() -> str:
    preferred_prefixes = [
        "patchright",
        "playwright-chrome",
        "playwright-firefox",
    ]
    names = [cfg.get("params", {}).get("name") for cfg in engines_config.engines]
    names = [name for name in names if isinstance(name, str) and name]
    for prefix in preferred_prefixes:
        for name in names:
            if name.startswith(prefix):
                return name
    if not names:
        raise AssertionError("No configured engines were found")
    return names[0]


async def _stop_engine_safely(engine: Any) -> None:
    if not engine:
        return
    try:
        await engine.stop()
    except Exception:
        pass


async def _check_headed_for_engine(engine_config: dict[str, Any]) -> CheckResult:
    engine_cls = engine_config["class"]
    params = dict(engine_config.get("params", {}))
    engine_name = params.get("name", engine_cls.__name__)

    if engine_config.get("requires_display", False):
        return CheckResult(engine_name, "SKIP", "engine explicitly requires display")

    if "headless" not in params:
        return CheckResult(engine_name, "SKIP", "engine has no configurable headless parameter")

    params["headless"] = False

    run_engine = None
    previous_display_env = _clear_display_env()
    try:
        run_engine = engine_cls(**params)
        await run_engine.start()
        await run_engine.navigate(DATA_URL)
        page_content = await run_engine.get_page_content()
        if not isinstance(page_content, str) or not page_content.strip():
            return CheckResult(engine_name, "FAIL", "page content is empty in headed mode without display vars")
        return CheckResult(
            engine_name,
            "OK",
            "engine started with headless=False and worked without display vars",
        )
    except Exception as e:
        return CheckResult(engine_name, "FAIL", f"runtime error: {e}")
    finally:
        await _stop_engine_safely(run_engine)
        _restore_display_env(previous_display_env)


def _print_result(result: CheckResult) -> None:
    print(f"[{result.status}] headed | {result.engine_name}: {result.message}")


def _summarize(results: list[CheckResult]) -> int:
    ok = sum(1 for r in results if r.status == "OK")
    fail = sum(1 for r in results if r.status == "FAIL")
    skip = sum(1 for r in results if r.status == "SKIP")
    print(f"\nSummary (headed): OK={ok}, FAIL={fail}, SKIP={skip}")
    return fail


async def _run(engine_names: list[str] | None) -> int:
    engine_configs = _filter_engine_configs(engine_names)
    print(f"Running headed/Xvfb checks for {len(engine_configs)} engines...")

    results: list[CheckResult] = []
    for engine_config in engine_configs:
        result = await _check_headed_for_engine(engine_config=engine_config)
        results.append(result)
        _print_result(result)

    return 1 if _summarize(results) > 0 else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run headed-mode checks in a headless-like env (DISPLAY/WAYLAND/MIR removed). "
            "Playwright-family engines may auto-start Xvfb."
        )
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        help="Optional list of engine names from config/engines.py; defaults to all configured engines.",
    )
    return parser.parse_args()


@pytest.mark.skipif(os.environ.get("RUN_ENGINE_TESTS") != "1", reason="Set RUN_ENGINE_TESTS=1 to run engine diagnostics")
def test_headed_xvfb_env() -> None:
    engine_name = _pick_engine_name()
    exit_code = asyncio.run(_run(engine_names=[engine_name]))
    assert exit_code == 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(engine_names=args.engines))


if __name__ == "__main__":
    raise SystemExit(main())
