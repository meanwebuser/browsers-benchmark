import re
from typing import Dict, List, Any

import pandas as pd

from config.benchmark_targets import benchmark_targets_config


def _active_bypass_targets() -> List[str]:
    return [target.name for target in benchmark_targets_config.bypass_targets.targets]


def _active_browser_data_targets() -> List[str]:
    return [target.name for target in benchmark_targets_config.browser_data_targets.targets]


def _base_engine_name(engine_name: str) -> str:
    """Collapse repeated run names like '<engine>__run3' to '<engine>'."""
    return re.sub(r"__run\d+$", "", engine_name)


def process_bypass_data(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Extract and process bypass data from benchmark results

    :param results: List of benchmark results for each engine
    :return: DataFrame containing bypass rates and engine stats
    """

    bypass_rows = []
    active_targets = _active_bypass_targets()
    active_target_set = set(active_targets)

    for engine_result in results:
        engine_name = _base_engine_name(engine_result["engine"])
        has_proxy = "proxy" in engine_name.lower()
        seen_targets = set()

        # base row with engine-level stats
        base_row = {
            "engine": engine_name,
            "has_proxy": has_proxy,
            "bypass_rate": engine_result["bypass_rate"],
            "avg_memory_mb": engine_result["average_memory_mb"],
            "avg_cpu_percent": engine_result["average_cpu_percent"],
            "startup_time_ms": engine_result.get("startup_time_ms"),
        }

        # per-target stats
        for target in engine_result.get("bypass_targets_results", []):
            target_name = target.get("target")
            if target_name not in active_target_set:
                continue

            row = base_row.copy()
            row.update(target)
            bypass_rows.append(row)
            seen_targets.add(target_name)

        # keep report aligned with the current target config
        for target_name in active_targets:
            if target_name in seen_targets:
                continue

            row = base_row.copy()
            row.update({
                "target": target_name,
                "url": None,
                "bypass": False,
                "error": "missing_target_in_results",
            })
            bypass_rows.append(row)

    return pd.DataFrame(bypass_rows)


def process_browser_data(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Extract and process browser data from benchmark results

    :param results: List of browser data results for each engine
    :return: DataFrame containing browser data metrics and engine stats
    """

    browser_data_rows = []
    active_targets = set(_active_browser_data_targets())

    for engine_result in results:
        engine_name = _base_engine_name(engine_result["engine"])
        has_proxy = "proxy" in engine_name.lower()

        # base row with engine info
        base_row = {
            "engine": engine_name,
            "has_proxy": has_proxy,
            "startup_time_ms": engine_result.get("startup_time_ms"),
        }

        # per-target metrics
        for target in engine_result.get("browser_data_targets_results", []):
            target_name = target.get("target")
            if target_name not in active_targets:
                continue

            row = base_row.copy()
            row.update(target)
            browser_data_rows.append(row)

    return pd.DataFrame(browser_data_rows)
