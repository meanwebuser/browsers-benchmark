#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.engines import engines_config
from config.settings import settings
from utils.proxy.proxy_manager import get_external_ip, proxy_manager

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


async def _stop_engine_safely(engine: Any) -> None:
    if not engine:
        return
    try:
        await engine.stop()
    except Exception:
        pass


async def _check_proxy_for_engine(
    engine_config: dict[str, Any],
    direct_ip: str | None,
    allow_missing_proxy: bool,
) -> CheckResult:
    engine_cls = engine_config["class"]
    params = dict(engine_config.get("params", {}))
    engine_name = params.get("name", engine_cls.__name__)

    probe_engine = None
    run_engine = None
    assigned_proxy = None

    try:
        probe_engine = engine_cls(**params)
        protocols = list(getattr(probe_engine, "supported_proxy_protocols", []) or [])
    except Exception as e:
        return CheckResult(engine_name, "FAIL", f"failed to inspect supported protocols: {e}")
    finally:
        await _stop_engine_safely(probe_engine)

    if not protocols:
        return CheckResult(engine_name, "SKIP", "engine does not support proxies")

    assigned_proxy = await proxy_manager.aget_proxy_by_protocol(
        supported_protocols=protocols,
        site=f"proxy-test:{engine_name}",
    )
    if not assigned_proxy:
        if allow_missing_proxy:
            return CheckResult(
                engine_name,
                "SKIP",
                f"no compatible proxy available (supports: {', '.join(protocols)})",
            )
        return CheckResult(
            engine_name,
            "FAIL",
            f"no compatible proxy available (supports: {', '.join(protocols)})",
        )

    params["proxy"] = assigned_proxy

    try:
        run_engine = engine_cls(**params)
        run_engine.known_direct_external_ip = direct_ip
        await run_engine.start()

        browser_ip = await run_engine.get_browser_external_ip()
        if not browser_ip:
            proxy_manager.mark_proxy_error(
                assigned_proxy,
                error_message="proxy check failed: browser external IP is empty",
                site=f"proxy-test:{engine_name}",
                mark_failed=False,
            )
            return CheckResult(engine_name, "FAIL", "browser external IP is empty")

        if direct_ip and browser_ip == direct_ip:
            proxy_manager.mark_proxy_error(
                assigned_proxy,
                error_message=f"proxy check failed: browser IP equals direct IP ({browser_ip})",
                site=f"proxy-test:{engine_name}",
                mark_failed=True,
            )
            return CheckResult(
                engine_name,
                "FAIL",
                f"browser IP equals direct IP ({browser_ip})",
            )

        proxy_manager.mark_proxy_success(assigned_proxy, site=f"proxy-test:{engine_name}")
        if direct_ip:
            return CheckResult(
                engine_name,
                "OK",
                f"proxy in use: browser_ip={browser_ip}, direct_ip={direct_ip}",
            )
        return CheckResult(engine_name, "OK", f"proxy in use: browser_ip={browser_ip}, direct_ip=unknown")
    except Exception as e:
        if assigned_proxy:
            proxy_manager.mark_proxy_error(
                assigned_proxy,
                error_message=f"proxy runtime error: {e}",
                site=f"proxy-test:{engine_name}",
                mark_failed=False,
            )
        return CheckResult(engine_name, "FAIL", f"runtime error: {e}")
    finally:
        await _stop_engine_safely(run_engine)
        if assigned_proxy:
            proxy_manager.release_proxy_lock(assigned_proxy)


async def _check_headed_in_headless_env_for_engine(engine_config: dict[str, Any]) -> CheckResult:
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


def _print_result(result: CheckResult, check_label: str) -> None:
    print(f"[{result.status}] {check_label} | {result.engine_name}: {result.message}")


def _summarize(results: list[CheckResult], check_label: str) -> int:
    ok = sum(1 for r in results if r.status == "OK")
    fail = sum(1 for r in results if r.status == "FAIL")
    skip = sum(1 for r in results if r.status == "SKIP")
    print(f"\nSummary ({check_label}): OK={ok}, FAIL={fail}, SKIP={skip}")
    return fail


async def _run(
    mode: str,
    engine_names: list[str] | None,
    allow_missing_proxy: bool,
) -> int:
    engine_configs = _filter_engine_configs(engine_names)
    total_failures = 0

    if mode in {"proxy", "all"}:
        print(f"Running proxy checks for {len(engine_configs)} engines...")
        direct_ip = get_external_ip(timeout=settings.proxy.test_timeout)
        if direct_ip:
            print(f"Direct IP: {direct_ip}")
        else:
            print("Direct IP: unavailable (will still verify browser IP is non-empty)")

        proxy_results: list[CheckResult] = []
        for engine_config in engine_configs:
            result = await _check_proxy_for_engine(
                engine_config=engine_config,
                direct_ip=direct_ip,
                allow_missing_proxy=allow_missing_proxy,
            )
            proxy_results.append(result)
            _print_result(result, "proxy")
        total_failures += _summarize(proxy_results, "proxy")

    if mode in {"headed", "all"}:
        print(f"\nRunning headed-in-headless-env checks for {len(engine_configs)} engines...")
        headed_results: list[CheckResult] = []
        for engine_config in engine_configs:
            result = await _check_headed_in_headless_env_for_engine(engine_config=engine_config)
            headed_results.append(result)
            _print_result(result, "headed")
        total_failures += _summarize(headed_results, "headed")

    return 1 if total_failures > 0 else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test script for (1) proxy usage and (2) headed launch in a headless-like env "
            "(DISPLAY/WAYLAND/MIR vars removed)."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["proxy", "headed", "all"],
        default="all",
        help="Which checks to run.",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        help="Optional list of engine names from config/engines.py; defaults to all configured engines.",
    )
    parser.add_argument(
        "--allow-missing-proxy",
        action="store_true",
        help="Treat missing compatible proxy as SKIP instead of FAIL.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(
        _run(
            mode=args.mode,
            engine_names=args.engines,
            allow_missing_proxy=args.allow_missing_proxy,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
