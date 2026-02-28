#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict

from config.benchmark_targets import benchmark_targets_config
from config.engines import engines_config
from config.settings import settings
from main import run_benchmark_for_engine
from utils.io import create_directory_structure, save_results
from utils.logging.logging import setup_logging
from utils.proxy.proxy_manager import proxy_manager, get_external_ip
from utils.report import generate_report


logger = logging.getLogger(__name__)


def _find_engine_config(engine_name: str) -> Dict[str, Any]:
    for engine_config in engines_config.engines:
        params = engine_config.get("params", {})
        if params.get("name") == engine_name:
            return engine_config
    raise ValueError(f"Engine '{engine_name}' not found in config/engines.py")


async def _run_single_engine(
        engine_name: str,
        use_proxy: bool,
        timestamp: str,
        targets: list[str] | None,
) -> int:
    result_path, _, screenshots_path = create_directory_structure(timestamp)

    safe_engine_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", engine_name)
    log_file = os.path.join(result_path, "logs", f"{safe_engine_name}.log")
    setup_logging(log_file=log_file, engine_name=engine_name)

    engine_config = _find_engine_config(engine_name)
    engine_cls = engine_config["class"]
    engine_params = dict(engine_config["params"])

    direct_external_ip = None
    proxy = None

    if use_proxy and settings.proxy.enabled:
        direct_external_ip = get_external_ip(timeout=settings.proxy.test_timeout)
        temp_engine = engine_cls(**engine_params)
        supported_protocols = temp_engine.supported_proxy_protocols

        if supported_protocols:
            proxy = await proxy_manager.aget_proxy_by_protocol(supported_protocols, site=engine_name)
            if not proxy:
                logger.error(
                    "No compatible proxy available for %s (supports: %s)",
                    engine_name,
                    ",".join(supported_protocols),
                )
                return 2
            logger.info("Assigned %s proxy to %s", proxy["protocol"], engine_name)
        else:
            logger.warning("%s does not support proxies. Running without proxy.", engine_name)
    else:
        logger.warning("Proxy usage is disabled for this run.")

    bypass_targets_all = [target.model_dump() for target in benchmark_targets_config.bypass_targets.targets]
    browser_data_targets_all = [target.model_dump() for target in benchmark_targets_config.browser_data_targets.targets]

    if targets:
        requested_targets = set(targets)
        bypass_targets = [target for target in bypass_targets_all if target["name"] in requested_targets]
        browser_data_targets = [target for target in browser_data_targets_all if target["name"] in requested_targets]
        found_targets = {target["name"] for target in bypass_targets + browser_data_targets}
        missing_targets = requested_targets - found_targets
        if missing_targets:
            logger.error(
                "Unknown target names provided: %s",
                ", ".join(sorted(missing_targets)),
            )
            return 1
    else:
        bypass_targets = bypass_targets_all
        browser_data_targets = browser_data_targets_all

    logger.info(
        "Running engine validation against bypass_targets=%d, browser_data_targets=%d",
        len(bypass_targets),
        len(browser_data_targets),
    )

    results = await run_benchmark_for_engine(
        engine_cls=engine_cls,
        engine_params=engine_params,
        bypass_targets=bypass_targets,
        browser_data_targets=browser_data_targets,
        screenshots_path=screenshots_path,
        proxy=proxy,
        direct_external_ip=direct_external_ip,
    )

    if not results:
        logger.error("Engine run returned no results.")
        return 1

    results_file = save_results(results, result_path)
    generate_report(results_file, result_path)
    logger.info("Single-engine validation completed. Results: %s", results_file)
    logger.info("Per-engine log file: %s", log_file)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all benchmark targets for one engine only."
    )
    parser.add_argument(
        "--engine",
        required=True,
        help="Engine name from config/engines.py (e.g. zendriver-chrome_headless).",
    )
    parser.add_argument(
        "--timestamp",
        default=datetime.now().strftime("%Y.%m.%d"),
        help="Results folder name under results/ (default: current date, e.g. 2026.02.27).",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable proxy for this validation run.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        help="Names of targets to run (space-separated). Defaults to all bypass and browser data targets.",
    )
    args = parser.parse_args()

    try:
        return asyncio.run(
            _run_single_engine(
                engine_name=args.engine,
                use_proxy=not args.no_proxy,
                timestamp=args.timestamp,
                targets=args.targets,
            )
        )
    except Exception as exc:
        setup_logging(engine_name=args.engine)
        logger.exception("Single-engine validation crashed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
