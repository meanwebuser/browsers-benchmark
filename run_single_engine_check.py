#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, Tuple

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


def _ordered_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _resolve_engine_names(
        engine_name: str | None,
        engine_names: list[str] | None,
        max_engines: int | None,
) -> list[str]:
    all_engine_names = [
        cfg.get("params", {}).get("name")
        for cfg in engines_config.engines
        if cfg.get("params", {}).get("name")
    ]

    if engine_name and engine_names:
        raise ValueError("Use either --engine or --engines, not both.")

    if engine_name:
        selected = [engine_name]
    elif engine_names:
        selected = list(engine_names)
    elif max_engines is not None:
        selected = list(all_engine_names)
    else:
        raise ValueError("Specify at least one of: --engine, --engines, --max-engines.")

    selected = _ordered_unique(selected)

    unknown = sorted(set(selected) - set(all_engine_names))
    if unknown:
        raise ValueError(
            "Unknown engine names provided: " + ", ".join(unknown)
        )

    if max_engines is not None:
        if max_engines <= 0:
            raise ValueError("--max-engines must be >= 1.")
        selected = selected[:max_engines]

    if not selected:
        raise ValueError("No engines selected after filters.")

    return selected


def _resolve_targets(
        targets: list[str] | None,
        max_targets: int | None,
) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    bypass_targets_all = [target.model_dump() for target in benchmark_targets_config.bypass_targets.targets]
    browser_data_targets_all = [target.model_dump() for target in benchmark_targets_config.browser_data_targets.targets]

    all_targets_by_name: Dict[str, Dict[str, Any]] = {}
    for target in bypass_targets_all + browser_data_targets_all:
        all_targets_by_name[target["name"]] = target

    if targets:
        selected_names = _ordered_unique(targets)
        missing_targets = sorted(set(selected_names) - set(all_targets_by_name.keys()))
        if missing_targets:
            raise ValueError(
                "Unknown target names provided: " + ", ".join(missing_targets)
            )
    else:
        selected_names = [target["name"] for target in (bypass_targets_all + browser_data_targets_all)]

    if max_targets is not None:
        if max_targets <= 0:
            raise ValueError("--max-targets must be >= 1.")
        selected_names = selected_names[:max_targets]

    if not selected_names:
        raise ValueError("No targets selected after filters.")

    selected_set = set(selected_names)
    bypass_targets = [target for target in bypass_targets_all if target["name"] in selected_set]
    browser_data_targets = [target for target in browser_data_targets_all if target["name"] in selected_set]

    return bypass_targets, browser_data_targets


async def _run_engine_selection(
        engine_names: list[str],
        use_proxy: bool,
        timestamp: str,
        targets: list[str] | None,
        max_targets: int | None,
) -> int:
    result_path, _, screenshots_path = create_directory_structure(timestamp)

    direct_external_ip = None
    if use_proxy and settings.proxy.enabled:
        direct_external_ip = get_external_ip(timeout=settings.proxy.test_timeout)
    else:
        logger.warning("Proxy usage is disabled for this run.")

    bypass_targets, browser_data_targets = _resolve_targets(targets=targets, max_targets=max_targets)

    logger.info(
        "Running engine validation for %d engine(s) against bypass_targets=%d, browser_data_targets=%d",
        len(engine_names),
        len(bypass_targets),
        len(browser_data_targets),
    )

    successful_runs = 0
    failed_runs = 0
    last_results_file: str | None = None

    for engine_name in engine_names:
        safe_engine_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", engine_name)
        log_file = os.path.join(result_path, "logs", f"{safe_engine_name}.log")
        setup_logging(log_file=log_file, engine_name=engine_name)

        engine_config = _find_engine_config(engine_name)
        engine_cls = engine_config["class"]
        engine_params = dict(engine_config["params"])

        proxy = None
        if use_proxy and settings.proxy.enabled:
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
                    failed_runs += 1
                    continue
                logger.info("Assigned %s proxy to %s", proxy["protocol"], engine_name)
            else:
                logger.warning("%s does not support proxies. Running without proxy.", engine_name)

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
            logger.error("Engine run returned no results for %s.", engine_name)
            failed_runs += 1
            continue

        last_results_file = save_results(results, result_path)
        successful_runs += 1
        logger.info("Engine validation completed for %s. Per-engine log file: %s", engine_name, log_file)

    if last_results_file:
        generate_report(last_results_file, result_path)
        logger.info("Validation completed. Results file: %s", last_results_file)
    else:
        logger.error("No results were generated for selected engines.")
        return 1

    if failed_runs > 0:
        logger.warning(
            "Validation finished with partial failures: success=%d, failed=%d",
            successful_runs,
            failed_runs,
        )
        return 1

    logger.info("Validation finished successfully: success=%d", successful_runs)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run selected benchmark targets for one or more engines."
    )
    parser.add_argument(
        "--engine",
        help="Single engine name from config/engines.py (e.g. zendriver-chrome_headless).",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        help="Multiple engine names from config/engines.py.",
    )
    parser.add_argument(
        "--max-engines",
        type=int,
        help="Limit selected engines to first N in the final selection order.",
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
        help="Names of targets to run (space-separated).",
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        help="Limit selected targets to first N in the final selection order.",
    )
    args = parser.parse_args()

    try:
        selected_engines = _resolve_engine_names(
            engine_name=args.engine,
            engine_names=args.engines,
            max_engines=args.max_engines,
        )
        return asyncio.run(
            _run_engine_selection(
                engine_names=selected_engines,
                use_proxy=not args.no_proxy,
                timestamp=args.timestamp,
                targets=args.targets,
                max_targets=args.max_targets,
            )
        )
    except Exception as exc:
        setup_logging(engine_name="engine-validation")
        logger.exception("Engine validation crashed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
