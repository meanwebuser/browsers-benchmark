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
from config.settings import settings
from utils.proxy.proxy_manager import get_external_ip, proxy_manager

pytestmark = pytest.mark.engine


@dataclass
class CheckResult:
    engine_name: str
    status: str  # OK | FAIL | SKIP
    message: str


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


def _print_result(result: CheckResult) -> None:
    print(f"[{result.status}] proxy | {result.engine_name}: {result.message}")


def _summarize(results: list[CheckResult]) -> int:
    ok = sum(1 for r in results if r.status == "OK")
    fail = sum(1 for r in results if r.status == "FAIL")
    skip = sum(1 for r in results if r.status == "SKIP")
    print(f"\nSummary (proxy): OK={ok}, FAIL={fail}, SKIP={skip}")
    return fail


async def _run(
    engine_names: list[str] | None,
    allow_missing_proxy: bool,
) -> int:
    settings.set_proxy_debug_verify_usage_for_tests(True)
    engine_configs = _filter_engine_configs(engine_names)
    print(f"Running proxy checks for {len(engine_configs)} engines...")

    direct_ip = get_external_ip(timeout=settings.proxy.test_timeout)
    if direct_ip:
        print(f"Direct IP: {direct_ip}")
    else:
        print("Direct IP: unavailable (will still verify browser IP is non-empty)")

    try:
        results: list[CheckResult] = []
        for engine_config in engine_configs:
            result = await _check_proxy_for_engine(
                engine_config=engine_config,
                direct_ip=direct_ip,
                allow_missing_proxy=allow_missing_proxy,
            )
            results.append(result)
            _print_result(result)

        return 1 if _summarize(results) > 0 else 0
    finally:
        settings.set_proxy_debug_verify_usage_for_tests(False)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run proxy validation across configured engines."
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


@pytest.mark.skipif(os.environ.get("RUN_ENGINE_TESTS") != "1", reason="Set RUN_ENGINE_TESTS=1 to run engine diagnostics")
def test_proxy_env() -> None:
    engine_name = _pick_engine_name()
    exit_code = asyncio.run(_run(engine_names=[engine_name], allow_missing_proxy=True))
    assert exit_code == 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(
        _run(
            engine_names=args.engines,
            allow_missing_proxy=args.allow_missing_proxy,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
