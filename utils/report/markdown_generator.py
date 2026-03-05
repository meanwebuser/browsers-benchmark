import os
import json
from typing import Dict, Any

import pandas as pd

import build_overall_score as overall_score
from config.report import report_settings
from config.settings import settings


def generate_markdown_summary(
        bypass_df: pd.DataFrame,
        browser_data_df: pd.DataFrame,
        output_dir: str,
        image_paths: Dict[str, str],
        raw_results: list[dict[str, Any]] | None = None,
) -> None:
    """
    Generate markdown summary of benchmark results

    :param bypass_df: DataFrame containing bypass results
    :param browser_data_df: DataFrame containing browser data results
    :param output_dir: Directory to save the generated markdown file
    :param image_paths: Dictionary mapping visualization names to their file paths
    :param raw_results: Raw benchmark results loaded from benchmark_results.json
    """

    with open(os.path.join(output_dir, report_settings.filenames.summary), "w", encoding="utf-8") as f:
        _write_report_header(f)
        _write_overall_score_section(f, raw_results)
        _write_bypass_section(f, bypass_df)
        _write_resource_section(f, bypass_df)
        _write_recaptcha_section(f, browser_data_df)
        _write_fingerprint_section(f, browser_data_df)
        _write_navigator_specs_section(f, bypass_df, browser_data_df)
        #_write_ip_section(f, browser_data_df)
        _write_visualization_sections(f, image_paths)


def _write_report_header(f) -> None:
    """
    Write the report header

    :param f: File object to write the header to
    """

    f.write("# Browser Benchmark Results Summary\n\n")
    f.write(f"*Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*\n\n")


def _write_overall_score_section(f, raw_results: list[dict[str, Any]] | None) -> None:
    f.write("## Overall Score (Privacy vs Performance)\n\n")

    if not raw_results:
        f.write("*No benchmark results available for overall scoring*\n\n")
        return

    valid_results = [
        row for row in raw_results
        if isinstance(row, dict) and overall_score._engine_has_any_data(row)
    ]
    if not valid_results:
        f.write("*No valid engine data available for overall scoring*\n\n")
        return

    cpu_count = overall_score._detect_cpu_count()
    ram_gb = overall_score._detect_ram_gb()

    scored = [
        overall_score._compute_engine_scores(
            engine_result=row,
            sites=None,
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            bypass_weight=0.5,
            bot_weight=0.5,
        )
        for row in valid_results
    ]
    overall_score._apply_derived_scores(scored)
    overall_score._sort_scored(scored)
    aggregated_scored = overall_score._aggregate_scored_by_engine(scored)
    overall_score._sort_scored_by_score(aggregated_scored)

    f.write("### Per Run\n\n")
    _write_overall_score_table(f, scored, include_run_count=False)
    f.write("### Averaged by Engine (mean across runs with same params)\n\n")
    _write_overall_score_table(f, aggregated_scored, include_run_count=True)


def _write_overall_score_table(f, rows: list[dict[str, Any]], include_run_count: bool) -> None:
    if include_run_count:
        f.write("| Engine | Runs | Score | Privacy | Performance | Windows/hour | Instances | Bottleneck | Full test s | Startup ms | Bypass % | Human % |\n")
        f.write("|-----------------|-----:|------:|--------:|------------:|-------------:|----------:|------------|------------:|-----------:|---------:|------------:|\n")
    else:
        f.write("| Engine | Privacy | Score | Performance | Windows/hour | Instances | Bottleneck | Full test s | Startup ms | Bypass % | Human % |\n")
        f.write("|-----------------|--------:|------:|------------:|-------------:|----------:|------------|------------:|-----------:|---------:|------------:|\n")

    for row in rows:
        if include_run_count:
            f.write(
                f"| {row.get('engine', 'unknown')} "
                f"| {overall_score._fmt(row.get('run_count'), 0)} "
                f"| {overall_score._fmt(row.get('overall_score'), 1)} "
                f"| {overall_score._fmt(row.get('privacy_score'), 1)} "
                f"| {overall_score._fmt(row.get('performance_score'), 1)} "
                f"| {overall_score._fmt(row.get('windows_per_hour'), 1)} "
                f"| {overall_score._fmt(row.get('estimated_instances'), 0)} "
                f"| {(row.get('bottleneck') or 'n/a')} "
                f"| {overall_score._fmt(row.get('full_test_duration_s'), 1)} "
                f"| {overall_score._fmt(row.get('startup_time_ms'), 1)} "
                f"| {overall_score._fmt(row.get('bypass_rate') * 100 if row.get('bypass_rate') is not None else None, 1)} "
                f"| {overall_score._fmt(row.get('bot_human_score') * 100 if row.get('bot_human_score') is not None else None, 1)} |\n"
            )
        else:
            f.write(
                f"| {row.get('engine', 'unknown')} "
                f"| {overall_score._fmt(row.get('privacy_score'), 1)} "
                f"| {overall_score._fmt(row.get('overall_score'), 1)} "
                f"| {overall_score._fmt(row.get('performance_score'), 1)} "
                f"| {overall_score._fmt(row.get('windows_per_hour'), 1)} "
                f"| {overall_score._fmt(row.get('estimated_instances'), 0)} "
                f"| {(row.get('bottleneck') or 'n/a')} "
                f"| {overall_score._fmt(row.get('full_test_duration_s'), 1)} "
                f"| {overall_score._fmt(row.get('startup_time_ms'), 1)} "
                f"| {overall_score._fmt(row.get('bypass_rate') * 100 if row.get('bypass_rate') is not None else None, 1)} "
                f"| {overall_score._fmt(row.get('bot_human_score') * 100 if row.get('bot_human_score') is not None else None, 1)} |\n"
            )

    f.write("\n\n")


def _write_bypass_section(f, bypass_df: pd.DataFrame) -> None:
    """
    Write the bypass rate section

    :param f: File object to write the section to
    :param bypass_df: DataFrame containing bypass results
    """

    f.write("## Overall Bypass Rate\n\n")

    if bypass_df.empty:
        f.write("*No bypass data available*\n\n")
        return

    bypass_by_engine = bypass_df.groupby("engine")["bypass"].mean().reset_index()
    bypass_by_engine["bypass_percent"] = bypass_by_engine["bypass"] * 100
    bypass_by_engine = bypass_by_engine.sort_values("bypass_percent", ascending=False)

    f.write("| Engine | Bypass Rate (%) |\n")
    f.write("|-----------------|----------------:|\n")
    for _, row in bypass_by_engine.iterrows():
        f.write(f"| {row['engine']} | {row['bypass_percent']:.1f} |\n")


def _write_resource_section(f, bypass_df: pd.DataFrame) -> None:
    """
    Write the resource usage section

    :param f: File object to write the section to
    :param bypass_df: DataFrame containing bypass results with resource usage
    """

    f.write("\n\n## Resource Usage Comparison\n\n")

    if bypass_df.empty:
        f.write("*No resource usage data available*\n\n")
        return

    resources_by_engine = bypass_df.groupby("engine")[["avg_memory_mb", "avg_cpu_percent"]].mean().reset_index()
    resources_by_engine = resources_by_engine.sort_values("avg_memory_mb")

    f.write("| Engine | Memory Usage (MB) | CPU Usage (%) |\n")
    f.write("|-----------------|------------------:|--------------:|\n")
    for _, row in resources_by_engine.iterrows():
        f.write(f"| {row['engine']} | {row['avg_memory_mb']:.1f} | {row['avg_cpu_percent']:.1f} |\n")

    f.write('\n\n')


def _write_recaptcha_section(f, browser_data_df: pd.DataFrame) -> None:
    """
    Write the reCAPTCHA section

    :param f: File object to write the section to
    :param browser_data_df: DataFrame containing browser data results with reCAPTCHA scores
    """

    f.write("## Recaptcha Scores\n\n")

    if browser_data_df.empty or "recaptcha_score" not in browser_data_df.columns:
        f.write("*No reCAPTCHA data available*\n\n")
        return

    recaptcha_data = browser_data_df.groupby("engine")["recaptcha_score"].mean().reset_index()

    if recaptcha_data.empty:
        f.write("*No reCAPTCHA data available*\n\n")
        return

    recaptcha_data = recaptcha_data.sort_values("recaptcha_score", ascending=False)

    f.write("| Engine | Recaptcha Score (0-1) |\n")
    f.write("|-----------------|--------------------:|\n")
    for _, row in recaptcha_data.iterrows():
        f.write(f"| {row['engine']} | {row['recaptcha_score']:.2f} |\n")

    f.write('\n\n')


def _write_fingerprint_section(f, browser_data_df: pd.DataFrame) -> None:
    """
    Write the Fingerprint section

    :param f: File object to write the section to
    :param browser_data_df: DataFrame containing browser data results with Fingerprint scores
    """

    f.write("## Fingerprint Demo Scores\n\n")
    if browser_data_df.empty or "engine" not in browser_data_df.columns:
        f.write("*No Fingerprint demo data available*\n\n")
        return

    suspect_col = "suspect_score"
    if suspect_col not in browser_data_df.columns:
        browser_data_df = browser_data_df.copy()
        browser_data_df[suspect_col] = pd.NA
    if "fingerprint_webrtc_ip" not in browser_data_df.columns:
        browser_data_df = browser_data_df.copy()
        browser_data_df["fingerprint_webrtc_ip"] = "Not detected"

    # calculate the metrics
    fingerprint_numeric_data = browser_data_df.groupby("engine")[[suspect_col]].mean().reset_index()

    if fingerprint_numeric_data.empty:
        f.write("*No Fingerprint demo data available*\n\n")
        return

    try:
        fingerprint_webrtc_ip_data = browser_data_df.groupby("engine")["fingerprint_webrtc_ip"].agg(
            lambda x: x.mode().iloc[0] if not x.isna().all() and len(x) > 0 else "Not detected"
        ).reset_index()
    except Exception:
        fingerprint_webrtc_ip_data = browser_data_df.groupby("engine")["fingerprint_webrtc_ip"].first().reset_index()
        fingerprint_webrtc_ip_data["fingerprint_webrtc_ip"] = fingerprint_webrtc_ip_data["fingerprint_webrtc_ip"].fillna("Not detected")

    fingerprint_file_data = None
    if "fingerprint_demo_file" in browser_data_df.columns:
        try:
            fingerprint_file_data = browser_data_df.groupby("engine")["fingerprint_demo_file"].agg(
                lambda x: x.mode().iloc[0] if not x.isna().all() and len(x) > 0 else ""
            ).reset_index()
        except Exception:
            fingerprint_file_data = browser_data_df.groupby("engine")["fingerprint_demo_file"].first().reset_index()
            fingerprint_file_data["fingerprint_demo_file"] = fingerprint_file_data["fingerprint_demo_file"].fillna("")

    # merge data and sort
    fingerprint_data = pd.merge(fingerprint_numeric_data, fingerprint_webrtc_ip_data, on="engine")
    if fingerprint_file_data is not None:
        fingerprint_data = pd.merge(fingerprint_data, fingerprint_file_data, on="engine", how="left")
    fingerprint_data = fingerprint_data.sort_values(suspect_col, ascending=True)

    f.write("| Engine | Suspect Score (%) | Raw File |\n")
    f.write("|-----------------|--------------:|----------:|\n")
    for _, row in fingerprint_data.iterrows():
        f.write(f"| {row['engine']} "
                f"| {row[suspect_col]:.2f} "
                f"| {row.get('fingerprint_demo_file', '') or row['fingerprint_webrtc_ip']} |\n")

    f.write('\n\n')


def _write_ip_section(f, browser_data_df: pd.DataFrame) -> None:
    """
    Write the IP section

    :param f: File object to write the section to
    :param browser_data_df: DataFrame containing browser data results with IP information
    """

    f.write("## IP (Ipify) \n\n")

    if "ip" not in browser_data_df.columns:
        f.write("*No IP data available*\n\n")
        return

    try:
        ip_data = browser_data_df.groupby("engine")["ip"].agg(
            lambda x: x.mode().iloc[0] if not x.isna().all() and len(x) > 0 else "Not detected"
        ).reset_index()
    except Exception:
        ip_data = browser_data_df.groupby("engine")["ip"].first().reset_index()
        ip_data["ip"] = ip_data["ip"].fillna("Not detected")

    f.write("| Engine | IP |\n")
    f.write("|-----------------|----------:|\n")
    for _, row in ip_data.iterrows():
        f.write(f"| {row['engine']} | {row['ip']} |\n")

    f.write('\n\n')


def _compact_cell(value, max_len: int = 90) -> str:
    if value is None:
        return "n/a"

    if isinstance(value, (dict, list, tuple)):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    else:
        value = str(value)

    value = value.replace("\n", " ").strip()
    if not value:
        return "n/a"

    return value if len(value) <= max_len else (value[: max_len - 1] + "…")


def _extract_signal_value(raw_attrs: dict, key: str):
    payload = raw_attrs.get(key)
    if isinstance(payload, dict):
        return payload.get("value")
    return None


def _find_client_hints(payload):
    interesting_keys = {
        "uaClientHints",
        "userAgentData",
        "brands",
        "fullVersionList",
        "platformVersion",
        "uaFullVersion",
        "architecture",
        "bitness",
        "mobile",
        "model",
    }

    queue = [payload]
    matches = {}

    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key in interesting_keys and key not in matches:
                    matches[key] = value
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    queue.append(item)

    return matches or None


def _extract_navigator_specs_from_file(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as src:
            payload = json.load(src)
    except Exception:
        return {
            "user_agent": "n/a",
            "platform": "n/a",
            "cpu": "n/a",
            "memory": "n/a",
            "architecture": "n/a",
            "languages": "n/a",
            "vendor": "n/a",
            "vendor_flavors": "n/a",
            "os_cpu": "n/a",
            "client_hints": "n/a",
        }

    products = payload.get("products", {}) if isinstance(payload, dict) else {}
    identification_data = products.get("identification", {}).get("data", {})
    browser_details = identification_data.get("browserDetails", {})
    raw_attrs = products.get("rawDeviceAttributes", {}).get("data", {})

    return {
        "user_agent": _compact_cell(browser_details.get("userAgent")),
        "platform": _compact_cell(_extract_signal_value(raw_attrs, "platform")),
        "cpu": _compact_cell(_extract_signal_value(raw_attrs, "hardwareConcurrency")),
        "memory": _compact_cell(_extract_signal_value(raw_attrs, "deviceMemory")),
        "architecture": _compact_cell(_extract_signal_value(raw_attrs, "architecture")),
        "languages": _compact_cell(_extract_signal_value(raw_attrs, "languages")),
        "vendor": _compact_cell(_extract_signal_value(raw_attrs, "vendor")),
        "vendor_flavors": _compact_cell(_extract_signal_value(raw_attrs, "vendorFlavors")),
        "os_cpu": _compact_cell(_extract_signal_value(raw_attrs, "osCpu")),
        "client_hints": _compact_cell(_find_client_hints(payload)),
    }


def _write_navigator_specs_section(f, bypass_df: pd.DataFrame, browser_data_df: pd.DataFrame) -> None:
    f.write("## Navigator Specs (Fingerprint Demo)\n\n")

    if bypass_df.empty and browser_data_df.empty:
        f.write("*No engine data available*\n\n")
        return

    if "fingerprint_demo_file" not in browser_data_df.columns:
        f.write("*No fingerprint demo files available*\n\n")
        return

    if not bypass_df.empty and "engine" in bypass_df.columns:
        engines = sorted(str(x) for x in bypass_df["engine"].dropna().unique())
    else:
        engines = sorted(str(x) for x in browser_data_df["engine"].dropna().unique())

    if not engines:
        f.write("*No engine data available*\n\n")
        return

    rows = []
    for engine in engines:
        file_path = ""
        target_df = browser_data_df[
            (browser_data_df.get("engine") == engine)
            & (browser_data_df.get("target") == "fingerprint_demo")
        ]
        if not target_df.empty:
            non_empty_paths = target_df["fingerprint_demo_file"].dropna().astype(str)
            non_empty_paths = non_empty_paths[non_empty_paths.str.strip() != ""]
            if not non_empty_paths.empty:
                file_path = non_empty_paths.iloc[0]

        if not file_path or not os.path.exists(file_path):
            specs = {
                "user_agent": "n/a",
                "platform": "n/a",
                "cpu": "n/a",
                "memory": "n/a",
                "architecture": "n/a",
                "languages": "n/a",
                "vendor": "n/a",
                "vendor_flavors": "n/a",
                "os_cpu": "n/a",
                "client_hints": "n/a",
            }
        else:
            specs = _extract_navigator_specs_from_file(file_path)

        specs["engine"] = engine
        rows.append(specs)

    if not rows:
        f.write("*No fingerprint demo files available*\n\n")
        return

    table_df = pd.DataFrame(rows).sort_values("engine")
    f.write("| Engine | User Agent | CPU | Memory | Platform | Architecture | Languages | Vendor | Vendor Flavors | OS CPU | Client Hints |\n")
    f.write("|-----------------|-----------------|----:|-------:|----------|--------------|-----------|--------|----------------|--------|--------------|\n")
    for _, row in table_df.iterrows():
        f.write(
            f"| {row['engine']} "
            f"| {row['user_agent']} "
            f"| {row['cpu']} "
            f"| {row['memory']} "
            f"| {row['platform']} "
            f"| {row['architecture']} "
            f"| {row['languages']} "
            f"| {row['vendor']} "
            f"| {row['vendor_flavors']} "
            f"| {row['os_cpu']} "
            f"| {row['client_hints']} |\n"
        )

    f.write('\n\n')


def _write_visualization_sections(f, image_paths: Dict[str, str]) -> None:
    """
    Write the visualization sections

    :param f: File object to write the sections to
    :param image_paths: Dictionary mapping visualization names to their file paths
    """

    # visual dashboard
    f.write("## Visual Dashboard\n\n")
    if "bypass_dashboard_image" in image_paths and image_paths["bypass_dashboard_image"]:
        f.write(
            f"![Bypass Dashboard]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['bypass_dashboard_image']))})\n\n")
    else:
        f.write("*No dashboard image available*\n\n")

    # timings dashboard
    f.write("## Timings Dashboard\n\n")
    if "timings_dashboard_image" in image_paths and image_paths["timings_dashboard_image"]:
        f.write(
            f"![Timings Dashboard]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['timings_dashboard_image']))})\n\n"
        )
    else:
        f.write("*No timings dashboard image available*\n\n")

    # detailed bypass charts
    f.write("## Bypass Detailed Charts\n\n")
    for key, title in [
        ("bypass_rate_image", "Bypass Rate"),
        ("bypass_protection_heatmap_image", "Bypass Protection Heatmap"),
        ("bypass_resource_usage_image", "Bypass Resource Usage"),
        ("bypass_load_time_image", "Bypass Load Time"),
    ]:
        if key in image_paths and image_paths[key]:
            f.write(f"### {title}\n\n")
            f.write(
                f"![{title}]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths[key]))})\n\n"
            )

    # detailed timings charts
    f.write("## Timings Detailed Charts\n\n")
    for key, title in [
        ("timing_startup_image", "Startup Time"),
        ("timing_bypass_image", "Bypass Navigation vs Full Test"),
        ("timing_browser_data_image", "Browser Data Navigation vs Full Test"),
        ("timing_overhead_image", "Timing Overhead"),
    ]:
        if key in image_paths and image_paths[key]:
            f.write(f"### {title}\n\n")
            f.write(
                f"![{title}]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths[key]))})\n\n"
            )

    # recaptcha visualization
    f.write("## Recaptcha Score Visualization\n\n")
    if "recaptcha_score_image" in image_paths and image_paths["recaptcha_score_image"]:
        f.write(
            f"![Recaptcha Scores]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['recaptcha_score_image']))})\n\n")
    else:
        f.write("*No reCAPTCHA image available*\n\n")

    # Fingerprint visualization
    f.write("## Fingerprint Demo Visualization\n\n")
    if "fingerprint_image" in image_paths and image_paths["fingerprint_image"]:
        f.write(
            f"![Fingerprint Scores]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['fingerprint_image']))})\n\n")
    else:
        f.write("*No Fingerprint image available*\n\n")

    # fingerprint_demo visualization
    f.write("## Fingerprint Demo (Browser Smart Signals)\n\n")
    if "fingerprint_demo_image" in image_paths and image_paths["fingerprint_demo_image"]:
        f.write(
            f"![Fingerprint Demo]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['fingerprint_demo_image']))})\n\n")
    else:
        f.write("*No Fingerprint Demo image available*\n\n")

    # incolumitas visualization
    f.write("## Incolumitas Visualization\n\n")
    if "incolumitas_image" in image_paths and image_paths["incolumitas_image"]:
        f.write(
            f"![Incolumitas]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['incolumitas_image']))})\n\n")
    else:
        f.write("*No Incolumitas image available*\n\n")

    # deviceandbrowserinfo visualization
    f.write("## DeviceAndBrowserInfo Visualization\n\n")
    if "deviceandbrowserinfo_image" in image_paths and image_paths["deviceandbrowserinfo_image"]:
        f.write(
            f"![DeviceAndBrowserInfo]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['deviceandbrowserinfo_image']))})\n\n")
    else:
        f.write("*No DeviceAndBrowserInfo image available*\n\n")

    # scan_fingerprint visualization
    f.write("## Fingerprint Scan Visualization\n\n")
    if "scan_fingerprint_image" in image_paths and image_paths["scan_fingerprint_image"]:
        f.write(
            f"![Fingerprint Scan]({os.path.join(settings.paths.media_dir, os.path.basename(image_paths['scan_fingerprint_image']))})\n\n")
    else:
        f.write("*No Fingerprint Scan image available*\n\n")
