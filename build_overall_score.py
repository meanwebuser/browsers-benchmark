import argparse
import json
import math
import os
import re
import statistics
from pathlib import Path
from typing import Any

import pandas as pd


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _normalize_unit_or_percent(value: Any) -> float | None:
    v = _safe_float(value)
    if v is None:
        return None
    if v > 1:
        v /= 100.0
    return max(0.0, min(1.0, v))


def _find_latest_valid_results_file(results_root: Path) -> Path:
    if not results_root.exists():
        raise FileNotFoundError(f"Results directory does not exist: {results_root}")

    candidates: list[tuple[float, Path]] = []
    for child in results_root.iterdir():
        if not child.is_dir():
            continue
        results_file = child / "benchmark_results.json"
        if not results_file.exists():
            continue
        candidates.append((results_file.stat().st_mtime, results_file))

    if not candidates:
        raise FileNotFoundError(
            f"No benchmark_results.json files found under: {results_root}"
        )

    for _, results_file in sorted(candidates, key=lambda item: item[0], reverse=True):
        try:
            payload = json.loads(results_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, list) and any(_engine_has_any_data(x) for x in payload):
            return results_file

    raise FileNotFoundError(
        f"Found benchmark_results.json files in {results_root}, but none contained valid data"
    )


def _resolve_results_file(args: argparse.Namespace) -> Path:
    if args.results_file:
        return Path(args.results_file).expanduser().resolve()
    if args.results_dir:
        return Path(args.results_dir).expanduser().resolve() / "benchmark_results.json"
    if args.results_path:
        path = Path(args.results_path).expanduser().resolve()
        if path.is_dir():
            results_file = path / "benchmark_results.json"
            if not results_file.exists() and (path / "progress_report.txt").exists():
                raise FileNotFoundError(
                    f"Results JSON not found: {results_file} "
                    f"(run is likely still in progress; progress_report.txt exists)"
                )
            return results_file
        return path
    return _find_latest_valid_results_file(Path(args.results_root).expanduser().resolve())


def _engine_has_any_data(engine_result: Any) -> bool:
    if not isinstance(engine_result, dict):
        return False
    bypass = engine_result.get("bypass_targets_results") or []
    browser_data = engine_result.get("browser_data_targets_results") or []
    if not isinstance(bypass, list) or not isinstance(browser_data, list):
        return False
    return bool(bypass or browser_data)


def _collect_site_names(results: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for engine_result in results:
        for row in engine_result.get("bypass_targets_results", []) or []:
            target = row.get("target")
            if isinstance(target, str) and target:
                names.add(target)
        for row in engine_result.get("browser_data_targets_results", []) or []:
            target = row.get("target")
            if isinstance(target, str) and target:
                names.add(target)
    return names


def _collect_bypass_target_names(results: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for engine_result in results:
        for row in engine_result.get("bypass_targets_results", []) or []:
            target = row.get("target")
            if isinstance(target, str) and target:
                names.add(target)
    return sorted(names)


def _collect_browser_target_names(results: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for engine_result in results:
        for row in engine_result.get("browser_data_targets_results", []) or []:
            target = row.get("target")
            if isinstance(target, str) and target:
                names.add(target)
    return sorted(names)


def _filter_rows_by_sites(rows: list[dict[str, Any]], sites: set[str] | None) -> list[dict[str, Any]]:
    if not sites:
        return rows
    return [row for row in rows if row.get("target") in sites]


def _base_engine_name(engine_name: str) -> str:
    # Collapse repeated runs like "<engine>__run3" into "<engine>".
    return re.sub(r"__run\d+$", "", engine_name)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.fmean(values)


def _extract_bot_signals(browser_rows: list[dict[str, Any]]) -> list[float]:
    signals: list[float] = []
    for row in browser_rows:
        recaptcha = _normalize_unit_or_percent(row.get("recaptcha_score"))  # higher better
        if recaptcha is not None:
            signals.append(recaptcha)

        for key in ("suspect_score",):  # lower better
            bot_prob = _normalize_unit_or_percent(row.get(key))
            if bot_prob is not None:
                signals.append(1.0 - bot_prob)

        for key in ("scan_fingerprint_bot_risk_score",):  # lower better
            scan = _normalize_unit_or_percent(row.get(key))
            if scan is not None:
                signals.append(1.0 - scan)

        for key in ("deviceandbrowserinfo_suspect_score",):  # lower better
            suscpect = _normalize_unit_or_percent(row.get(key))
            if suscpect is not None:
                signals.append(1.0 - suscpect)

    return signals


def _extract_run_extra_columns(
        engine_result: dict[str, Any],
        bypass_targets: list[str],
        browser_targets: list[str],
        sites: set[str] | None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    bypass_rows_all = engine_result.get("bypass_targets_results") or []
    browser_rows_all = engine_result.get("browser_data_targets_results") or []
    bypass_rows = _filter_rows_by_sites(bypass_rows_all, sites)
    browser_rows = _filter_rows_by_sites(browser_rows_all, sites)

    bypass_by_target: dict[str, list[bool]] = {}
    for row in bypass_rows:
        target = row.get("target")
        if not isinstance(target, str) or not target:
            continue
        ok = bool(row.get("bypass")) and not row.get("error")
        bypass_by_target.setdefault(target, []).append(ok)

    for target in bypass_targets:
        values = bypass_by_target.get(target, [])
        prob = _mean([1.0 if v else 0.0 for v in values]) if values else None
        extra[f"bypass_prob__{target}"] = (prob * 100.0) if prob is not None else None

    signals_by_target: dict[str, list[float]] = {}
    ips_by_target: dict[str, set[str]] = {}
    all_ips: set[str] = set()
    for row in browser_rows:
        target = row.get("target")
        if not isinstance(target, str) or not target:
            continue

        target_signals = _extract_bot_signals([row])
        if target_signals:
            signals_by_target.setdefault(target, []).extend(target_signals)

        ip = row.get("ip")
        if isinstance(ip, str) and ip.strip():
            all_ips.add(ip.strip())
            ips_by_target.setdefault(target, set()).add(ip.strip())

    for target in browser_targets:
        human = _mean(signals_by_target.get(target, []))
        extra[f"human_score__{target}"] = (human * 100.0) if human is not None else None
        target_ips = sorted(ips_by_target.get(target, set()))
        extra[f"ip__{target}"] = ", ".join(target_ips) if target_ips else None

    extra["ip_list"] = ", ".join(sorted(all_ips)) if all_ips else None
    extra["engine_error"] = engine_result.get("error")
    extra["engine_timestamp"] = engine_result.get("timestamp")
    return extra


def _estimate_instance_capacity_by_ram(
        ram_gb: float,
        per_instance_memory_mb: float | None,
) -> int | None:
    if per_instance_memory_mb is None or per_instance_memory_mb <= 0:
        return None

    total_memory_mb = max(ram_gb, 0.0) * 1024.0
    return max(1, max(0, int(total_memory_mb // per_instance_memory_mb)))



def _estimate_instance_capacity_by_cpu(
        cpu_count: float,
        per_instance_cpu_percent: float | None,
) -> int | None:
    if per_instance_cpu_percent is None or per_instance_cpu_percent <= 0:
        return None

    total_cpu_capacity = max(cpu_count, 1.0) * 100.0
    return max(1, max(0, int(total_cpu_capacity // per_instance_cpu_percent)))


def _compute_engine_scores(
        engine_result: dict[str, Any],
        sites: set[str] | None,
        cpu_count: float,
        ram_gb: float,
        bypass_weight: float,
        bot_weight: float,
) -> dict[str, Any]:
    engine_name = str(engine_result.get("engine") or "unknown")

    bypass_rows_all = engine_result.get("bypass_targets_results") or []
    browser_rows_all = engine_result.get("browser_data_targets_results") or []

    bypass_rows = _filter_rows_by_sites(bypass_rows_all, sites)
    browser_rows = _filter_rows_by_sites(browser_rows_all, sites)

    if sites and not bypass_rows and not browser_rows:
        return {
            "engine": engine_name,
            "privacy_score": None,
            "performance_score": None,
            "bypass_rate": None,
            "bot_human_score": None,
            "full_test_duration_s": None,
            "startup_time_ms": None,
            "estimated_instances": None,
            "estimated_instances_ram": None,
            "estimated_instances_cpu": None,
            "bottleneck": None,
            "windows_per_hour": None,
            "avg_memory_mb": None,
            "avg_cpu_percent": None,
        }

    bypass_rate: float | None = None
    if bypass_rows:
        passed = sum(1 for row in bypass_rows if bool(row.get("bypass")) and not row.get("error"))
        bypass_rate = passed / len(bypass_rows)

    bot_signals = _extract_bot_signals(browser_rows)
    bot_human_score = _mean(bot_signals)

    weighted_components: list[tuple[float, float]] = []
    if bypass_rate is not None and bypass_weight > 0:
        weighted_components.append((bypass_weight, bypass_rate))
    if bot_human_score is not None and bot_weight > 0:
        weighted_components.append((bot_weight, bot_human_score))

    privacy_score = None
    if weighted_components:
        total_weight = sum(weight for weight, _ in weighted_components)
        combined = sum(weight * value for weight, value in weighted_components) / total_weight
        privacy_score = combined * 100.0

    bypass_rows_for_perf = bypass_rows if bypass_rows else bypass_rows_all
    perf_rows = [row for row in bypass_rows_for_perf if row.get("error") in (None, "")]
    load_samples = [
        v for v in (_safe_float(row.get("load_time_ms")) for row in perf_rows)
        if v is not None and v > 0
    ]
    mem_samples = [
        v for v in (_safe_float(row.get("memory_mb")) for row in perf_rows)
        if v is not None and v > 0
    ]
    cpu_samples = [
        v for v in (_safe_float(row.get("cpu_percent")) for row in perf_rows)
        if v is not None and v > 0
    ]
    duration_rows = [
        row
        for row in (bypass_rows + browser_rows)
        if row.get("error") in (None, "")
    ]
    duration_samples_ms = [
        v for v in (_safe_float(row.get("test_duration_ms")) for row in duration_rows)
        if v is not None and v > 0
    ]

    startup_time_ms = _safe_float(engine_result.get("startup_time_ms"))
    if startup_time_ms is None or startup_time_ms <= 0:
        # Backward compatibility for old result files that don't have startup_time_ms yet.
        startup_time_ms = statistics.median(load_samples) if load_samples else None
    full_test_duration_ms = statistics.median(duration_samples_ms) if duration_samples_ms else None
    full_test_duration_s = full_test_duration_ms / 1000.0 if full_test_duration_ms is not None else None
    avg_memory_mb = _mean(mem_samples)
    avg_cpu_percent = _mean(cpu_samples)

    if avg_memory_mb is None:
        avg_memory_mb = _safe_float(engine_result.get("average_memory_mb"))
    if avg_cpu_percent is None:
        avg_cpu_percent = _safe_float(engine_result.get("average_cpu_percent"))

    estimated_instances_ram = _estimate_instance_capacity_by_ram(
        ram_gb=ram_gb,
        per_instance_memory_mb=avg_memory_mb,
    )
    estimated_instances_cpu = _estimate_instance_capacity_by_cpu(
        cpu_count=cpu_count,
        per_instance_cpu_percent=avg_cpu_percent,
    )
    estimated_instances: int | None = None
    bottleneck: str | None = None
    if estimated_instances_ram is not None and estimated_instances_cpu is not None:
        estimated_instances = min(estimated_instances_ram, estimated_instances_cpu)
        if estimated_instances_ram < estimated_instances_cpu:
            bottleneck = "ram"
        elif estimated_instances_cpu < estimated_instances_ram:
            bottleneck = "cpu"
        else:
            bottleneck = "balanced"
    elif estimated_instances_ram is not None:
        estimated_instances = estimated_instances_ram
        bottleneck = "ram"
    elif estimated_instances_cpu is not None:
        estimated_instances = estimated_instances_cpu
        bottleneck = "cpu"

    windows_per_hour = None
    if (
        full_test_duration_s is not None
        and full_test_duration_s > 0
        and estimated_instances is not None
    ):
        windows_per_hour = estimated_instances * (3_600.0 / full_test_duration_s)

    return {
        "engine": engine_name,
        "privacy_score": privacy_score,
        "performance_score": None,
        "bypass_rate": bypass_rate,
        "bot_human_score": bot_human_score,
        "full_test_duration_s": full_test_duration_s,
        "startup_time_ms": startup_time_ms,
        "estimated_instances": estimated_instances,
        "estimated_instances_ram": estimated_instances_ram,
        "estimated_instances_cpu": estimated_instances_cpu,
        "bottleneck": bottleneck,
        "windows_per_hour": windows_per_hour,
        "avg_memory_mb": avg_memory_mb,
        "avg_cpu_percent": avg_cpu_percent,
    }


def _detect_cpu_count() -> float:
    cpu = os.cpu_count()
    return float(cpu) if cpu and cpu > 0 else 1.0


def _detect_ram_gb() -> float:
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024.0 ** 3)
    except Exception:
        pass

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    kb = float(parts[1])
                    return kb / (1024.0 ** 2)
        except Exception:
            pass

    return 8.0


def _fmt(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    formatted = f"{value:,.{digits}f}"
    return formatted.replace(",", " ")


def _apply_derived_scores(rows: list[dict[str, Any]]) -> None:
    throughput_values = [
        row["windows_per_hour"] for row in rows
        if row.get("windows_per_hour") is not None and row["windows_per_hour"] > 0
    ]
    max_throughput = max(throughput_values) if throughput_values else None

    for row in rows:
        throughput = row.get("windows_per_hour")
        if max_throughput and throughput is not None and throughput > 0:
            row["performance_score"] = (throughput / max_throughput) * 100.0
        elif throughput is not None and throughput == 0:
            row["performance_score"] = 0.0
        else:
            row["performance_score"] = None

        privacy = row.get("privacy_score")
        row["overall_score"] = (
            (privacy / 100.0) * throughput
            if privacy is not None and throughput is not None
            else None
        )


def _sort_scored(rows: list[dict[str, Any]]) -> None:
    rows.sort(
        key=lambda item: (
            item["privacy_score"] if item.get("privacy_score") is not None else -1,
            item["performance_score"] if item.get("performance_score") is not None else -1,
        ),
        reverse=True,
    )


def _sort_scored_by_score(rows: list[dict[str, Any]]) -> None:
    rows.sort(
        key=lambda item: (
            item["overall_score"] if item.get("overall_score") is not None else -1,
            item["privacy_score"] if item.get("privacy_score") is not None else -1,
            item["performance_score"] if item.get("performance_score") is not None else -1,
        ),
        reverse=True,
    )


def _aggregate_scored_by_engine(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _base_engine_name(str(row.get("engine") or "unknown"))
        groups.setdefault(key, []).append(row)

    numeric_fields = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if key not in {"engine", "bottleneck", "run_count"}
            and _safe_float(value) is not None
        }
    )

    aggregated: list[dict[str, Any]] = []
    for engine_name, items in groups.items():
        merged: dict[str, Any] = {
            "engine": engine_name,
            "run_count": len(items),
        }

        for field in numeric_fields:
            values = [_safe_float(item.get(field)) for item in items]
            clean = [v for v in values if v is not None]
            merged[field] = _mean(clean)

        bottlenecks = [str(item.get("bottleneck")) for item in items if item.get("bottleneck")]
        merged["bottleneck"] = statistics.multimode(bottlenecks)[0] if bottlenecks else None
        merged["run_engines"] = ", ".join(sorted(str(item.get("engine")) for item in items))
        merged["ip_list"] = ", ".join(
            sorted(
                {
                    ip.strip()
                    for item in items
                    for ip in str(item.get("ip_list") or "").split(",")
                    if ip.strip()
                }
            )
        ) or None
        aggregated.append(merged)

    return aggregated


def _ordered_export_columns(rows: list[dict[str, Any]], include_runs: bool) -> list[str]:
    base = [
        "engine",
        *(["run_count"] if include_runs else []),
        "overall_score",
        "privacy_score",
        "performance_score",
        "windows_per_hour",
        "estimated_instances",
        "bottleneck",
        "full_test_duration_s",
        "startup_time_ms",
        "bypass_rate",
        "bot_human_score",
        "avg_memory_mb",
        "avg_cpu_percent",
        "ip_list",
        "engine_error",
        "engine_timestamp",
        "run_engines",
    ]
    existing = {key for row in rows for key in row.keys()}
    ordered = [col for col in base if col in existing]
    extra = sorted(existing - set(ordered))
    return ordered + extra


def _export_excel_like(
        per_run_rows: list[dict[str, Any]],
        aggregated_rows: list[dict[str, Any]],
        output_path: Path,
) -> None:
    per_run_df = pd.DataFrame(per_run_rows)
    per_run_df = per_run_df.reindex(columns=_ordered_export_columns(per_run_rows, include_runs=False))

    aggregated_df = pd.DataFrame(aggregated_rows)
    aggregated_df = aggregated_df.reindex(columns=_ordered_export_columns(aggregated_rows, include_runs=True))

    try:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            per_run_df.to_excel(writer, index=False, sheet_name="Per-run scores")
            aggregated_df.to_excel(writer, index=False, sheet_name="Averaged by engine")
        print(f"Saved Excel: {output_path}")
        return
    except Exception:
        base = output_path.with_suffix("")
        per_run_csv = Path(f"{base}_per_run.csv")
        avg_csv = Path(f"{base}_averaged.csv")
        per_run_df.to_csv(per_run_csv, index=False)
        aggregated_df.to_csv(avg_csv, index=False)
        print(f"Excel export unavailable (install openpyxl). Saved CSVs: {per_run_csv}, {avg_csv}")


def _print_table(
        rows: list[dict[str, Any]],
        title: str | None = None,
        include_run_count: bool = False,
) -> None:
    if title:
        print(title)
    if include_run_count:
        headers = [
            "Engine",
            "Runs",
            "Score",
            "Privacy",
            "Performance",
            "Windows/hour",
            "Instances",
            "Bottleneck",
            "Full test s",
            "Startup ms",
            "Bypass %",
            "Human",
        ]
    else:
        headers = [
            "Engine",
            "Privacy",
            "Score",
            "Performance",
            "Windows/hour",
            "Instances",
            "Bottleneck",
            "Full test s",
            "Startup ms",
            "Bypass %",
            "Human",
        ]
    table: list[list[str]] = []
    for row in rows:
        if include_run_count:
            table.append(
                [
                    str(row["engine"]),
                    _fmt(row.get("run_count"), 0),
                    _fmt(row.get("overall_score"), 1),
                    _fmt(row["privacy_score"], 1),
                    _fmt(row["performance_score"], 1),
                    _fmt(row["windows_per_hour"], 1),
                    _fmt(row["estimated_instances"], 0),
                    str(row["bottleneck"] or "n/a"),
                    _fmt(row["full_test_duration_s"], 1),
                    _fmt(row["startup_time_ms"], 1),
                    _fmt(row["bypass_rate"] * 100 if row["bypass_rate"] is not None else None, 1),
                    _fmt(row["bot_human_score"] * 100 if row["bot_human_score"] is not None else None, 1),
                ]
            )
        else:
            table.append(
                [
                    str(row["engine"]),
                    _fmt(row["privacy_score"], 1),
                    _fmt(row.get("overall_score"), 1),
                    _fmt(row["performance_score"], 1),
                    _fmt(row["windows_per_hour"], 1),
                    _fmt(row["estimated_instances"], 0),
                    str(row["bottleneck"] or "n/a"),
                    _fmt(row["full_test_duration_s"], 1),
                    _fmt(row["startup_time_ms"], 1),
                    _fmt(row["bypass_rate"] * 100 if row["bypass_rate"] is not None else None, 1),
                    _fmt(row["bot_human_score"] * 100 if row["bot_human_score"] is not None else None, 1),
                ]
            )

    widths = [len(h) for h in headers]
    for line in table:
        for i, value in enumerate(line):
            widths[i] = max(widths[i], len(value))

    def _render_line(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(_render_line(headers))
    print("-+-".join("-" * w for w in widths))
    for line in table:
        print(_render_line(line))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build privacy vs performance scores from benchmark_results.json. "
            "By default, uses the latest valid run under results/."
        )
    )
    parser.add_argument(
        "results_path",
        nargs="?",
        help="Optional run directory or path to benchmark_results.json",
    )
    parser.add_argument("--results-file", help="Path to benchmark_results.json")
    parser.add_argument("--results-dir", help="Run directory containing benchmark_results.json")
    parser.add_argument(
        "--results-root",
        default="results",
        help="Root results directory (default: results)",
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        help=(
            "Only include selected target names in scoring "
            "(e.g. google_search recaptcha_score scan_fingerprint). Default: all sites"
        ),
    )
    parser.add_argument(
        "--cpu-count",
        type=float,
        help="Override host CPU core count used for performance estimation",
    )
    parser.add_argument(
        "--ram-gb",
        type=float,
        help="Override host RAM (GB) used for performance estimation",
    )
    parser.add_argument(
        "--bypass-weight",
        type=float,
        default=0.5,
        help="Weight for bypass rate in privacy score (default: 0.5)",
    )
    parser.add_argument(
        "--bot-weight",
        type=float,
        default=0.5,
        help="Weight for bot/human signals in privacy score (default: 0.5)",
    )
    parser.add_argument(
        "--output-file",
        help="Optional path to save computed scores as JSON",
    )
    parser.add_argument(
        "--excel-file",
        help="Optional path to save Excel report (.xlsx). Falls back to CSV if openpyxl is unavailable.",
    )
    args = parser.parse_args()

    results_file = _resolve_results_file(args)
    if not results_file.exists():
        raise FileNotFoundError(f"Results JSON not found: {results_file}")

    payload = json.loads(results_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in: {results_file}")

    results: list[dict[str, Any]] = [row for row in payload if isinstance(row, dict) and _engine_has_any_data(row)]
    if not results:
        raise ValueError(f"No valid engine data found in: {results_file}")

    available_sites = _collect_site_names(results)
    selected_sites: set[str] | None = None
    if args.sites:
        selected_sites = set(args.sites)
        unknown = sorted(site for site in selected_sites if site not in available_sites)
        if unknown:
            print(f"Warning: requested sites not found in results: {', '.join(unknown)}")

    cpu_count = args.cpu_count if args.cpu_count and args.cpu_count > 0 else _detect_cpu_count()
    ram_gb = args.ram_gb if args.ram_gb and args.ram_gb > 0 else _detect_ram_gb()

    bypass_targets = _collect_bypass_target_names(results)
    browser_targets = _collect_browser_target_names(results)
    scored: list[dict[str, Any]] = []
    for row in results:
        score_row = _compute_engine_scores(
            engine_result=row,
            sites=selected_sites,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            bypass_weight=max(0.0, args.bypass_weight),
            bot_weight=max(0.0, args.bot_weight),
        )
        score_row.update(
            _extract_run_extra_columns(
                engine_result=row,
                bypass_targets=bypass_targets,
                browser_targets=browser_targets,
                sites=selected_sites,
            )
        )
        scored.append(score_row)

    _apply_derived_scores(scored)
    _sort_scored(scored)
    aggregated_scored = _aggregate_scored_by_engine(scored)
    _sort_scored_by_score(aggregated_scored)

    print(f"Results source: {results_file}")
    print(f"Hardware basis: cpu_count={cpu_count:.2f}, ram_gb={ram_gb:.2f}")
    if selected_sites:
        print(f"Included sites ({len(selected_sites)}): {', '.join(sorted(selected_sites))}")
    else:
        print(f"Included sites: all ({len(available_sites)})")
    print()
    _print_table(scored, title="Per-run scores:")
    print()
    _print_table(
        aggregated_scored,
        title="Averaged by engine (mean across runs with same params):",
        include_run_count=True,
    )

    excel_path = (
        Path(args.excel_file).expanduser().resolve()
        if args.excel_file
        else results_file.parent / "overall_scores.xlsx"
    )
    _export_excel_like(scored, aggregated_scored, excel_path)

    if args.output_file:
        output_path = Path(args.output_file).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_payload = {
            "results_file": str(results_file),
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
            "selected_sites": sorted(selected_sites) if selected_sites else sorted(available_sites),
            "axes": [
                {
                    "engine": row["engine"],
                    "privacy_score": row["privacy_score"],
                    "overall_score": row["overall_score"],
                    "performance_score": row["performance_score"],
                    "windows_per_hour": row["windows_per_hour"],
                    "estimated_instances": row["estimated_instances"],
                    "estimated_instances_ram": row["estimated_instances_ram"],
                    "estimated_instances_cpu": row["estimated_instances_cpu"],
                    "bottleneck": row["bottleneck"],
                    "full_test_duration_s": row["full_test_duration_s"],
                    "startup_time_ms": row["startup_time_ms"],
                    "bypass_rate": row["bypass_rate"],
                    "bot_human_score": row["bot_human_score"],
                }
                for row in scored
            ],
            "axes_aggregated": [
                {
                    "engine": row["engine"],
                    "run_count": row["run_count"],
                    "privacy_score": row["privacy_score"],
                    "overall_score": row["overall_score"],
                    "performance_score": row["performance_score"],
                    "windows_per_hour": row["windows_per_hour"],
                    "estimated_instances": row["estimated_instances"],
                    "estimated_instances_ram": row["estimated_instances_ram"],
                    "estimated_instances_cpu": row["estimated_instances_cpu"],
                    "bottleneck": row["bottleneck"],
                    "full_test_duration_s": row["full_test_duration_s"],
                    "startup_time_ms": row["startup_time_ms"],
                    "bypass_rate": row["bypass_rate"],
                    "bot_human_score": row["bot_human_score"],
                }
                for row in aggregated_scored
            ],
        }
        output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
        print()
        print(f"Saved score JSON: {output_path}")


if __name__ == "__main__":
    main()
