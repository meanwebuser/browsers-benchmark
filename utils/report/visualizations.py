import json
import os
from typing import Dict, List, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from config.report import report_settings

THEME_GRID_COLOR = "#d1daeb"

sns.set_theme(
    context="talk",
    style="whitegrid",
    palette="viridis",
    rc={
        "figure.facecolor": "#fdfdfd",
        "axes.facecolor": "#fbfcff",
        "axes.edgecolor": "#3c4043",
        "axes.labelcolor": "#111",
        "axes.titleweight": "bold",
        "axes.titlepad": 14,
        "grid.color": THEME_GRID_COLOR,
        "grid.linestyle": report_settings.colors.grid_linestyle,
        "grid.alpha": report_settings.colors.grid_alpha,
        "legend.frameon": False,
        "font.family": "DejaVu Sans",
    }
)


def _resolve_fingerprint_trust_column(df: pd.DataFrame) -> str | None:
    if "fingerprint_untrust_score" in df.columns:
        return "fingerprint_untrust_score"
    if "fingerprint_trust_score" in df.columns:
        return "fingerprint_trust_score"
    return None


def _resolve_fingerprint_suspect_column(df: pd.DataFrame) -> str | None:
    if "suspect_score" in df.columns:
        return "suspect_score"
    if "fingerprint_bot_score" in df.columns:
        return "fingerprint_bot_score"
    return None


def _collect_bool_values(payload: Any) -> list[bool]:
    values: list[bool] = []
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, bool):
            values.append(current)
    return values


def _load_deviceandbrowserinfo_signal_ratio(file_path: Any) -> float | None:
    path = str(file_path or "").strip()
    if not path or not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    details_payload = payload.get("details") if isinstance(payload, dict) else None
    bool_values = _collect_bool_values(details_payload if details_payload is not None else payload)
    if not bool_values:
        return None
    return (sum(1 for value in bool_values if value) / len(bool_values)) * 100.0


def _target_df(df: pd.DataFrame, target_name: str) -> pd.DataFrame:
    if df.empty or "target" not in df.columns:
        return pd.DataFrame()
    return df[df["target"] == target_name].copy()


def generate_bypass_dashboard_image(df: pd.DataFrame, output_dir: str) -> str:
    """
    Generate a dashboard of bypass benchmark results

    :param df: DataFrame containing bypass benchmark results
    :param output_dir: Directory to save the generated image
    """

    plt.figure(figsize=report_settings.visualization.figure_size_large)
    plt.suptitle("Browser Engine Benchmark Results", fontsize=24, y=0.99)

    if df.empty:
        plt.text(0.5, 0.5, "No bypass data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.bypass_dashboard)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    # calculate engines sorted by bypass rate for ordering
    engines = df.groupby("engine")["bypass"].mean().sort_values(ascending=False).index.tolist()
    colors = plt.cm.get_cmap('viridis')(np.linspace(0, 1, len(engines)))
    engine_colors = {engine: color for engine, color in zip(engines, colors)}

    # create subplots
    _create_bypass_rate_subplot(df, engine_colors)
    _create_protection_heatmap_subplot(df, engines)
    _create_resource_usage_subplot(df)
    _create_load_time_subplot(df)

    # layout adjustments
    plt.tight_layout(rect=(0, 0, 1.0, 0.96))

    # add note
    _add_dashboard_note()

    image_path = os.path.join(output_dir, report_settings.filenames.bypass_dashboard)
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')

    return image_path


def generate_timings_dashboard_image(
        bypass_df: pd.DataFrame,
        browser_data_df: pd.DataFrame,
        output_dir: str
) -> str:
    """Generate a multi-panel dashboard with startup/navigation/full-test timings."""

    plt.figure(figsize=report_settings.visualization.figure_size_large)
    plt.suptitle("Browser Engine Timings Dashboard", fontsize=24, y=0.99)

    if bypass_df.empty and browser_data_df.empty:
        plt.text(0.5, 0.5, "No timing data available", ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.timings_dashboard)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    _create_startup_timing_subplot(bypass_df, browser_data_df)
    _create_bypass_timing_subplot(bypass_df)
    _create_browser_data_timing_subplot(browser_data_df)
    _create_overhead_timing_subplot(bypass_df, browser_data_df)

    plt.tight_layout(rect=(0, 0, 1.0, 0.96))
    image_path = os.path.join(output_dir, report_settings.filenames.timings_dashboard)
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def _save_no_data_image(image_path: str, title: str, message: str) -> str:
    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title(title, fontsize=16)
    plt.text(0.5, 0.5, message, ha='center', va='center', fontsize=14)
    plt.xticks([])
    plt.yticks([])
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def generate_bypass_detailed_images(df: pd.DataFrame, output_dir: str) -> Dict[str, str]:
    """Generate separate charts for each block of bypass_dashboard."""

    images: Dict[str, str] = {}

    # Bypass rate
    image_path = os.path.join(output_dir, report_settings.filenames.bypass_rate)
    if df.empty:
        images["bypass_rate_image"] = _save_no_data_image(image_path, "Bypass Rate by Browser", "No bypass data available")
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        bypass_by_engine = df.groupby("engine")["bypass"].mean().reset_index()
        bypass_by_engine["bypass_percent"] = bypass_by_engine["bypass"] * 100
        bypass_by_engine = bypass_by_engine.sort_values("bypass_percent", ascending=False)
        bars = sns.barplot(x="engine", y="bypass_percent", hue="engine", data=bypass_by_engine, palette="viridis", legend=False)
        for i, v in enumerate(bypass_by_engine["bypass_percent"]):
            bars.text(i, v + 1, f"{v:.1f}%", ha='center', va='bottom', fontsize=9)
        plt.title("Bypass Rate by Browser", fontsize=16)
        plt.ylabel("Bypass Rate (%)", fontsize=12)
        plt.xticks(rotation=45, ha="right", fontsize=10)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["bypass_rate_image"] = image_path

    # Protection heatmap
    image_path = os.path.join(output_dir, report_settings.filenames.bypass_protection_heatmap)
    if df.empty:
        images["bypass_protection_heatmap_image"] = _save_no_data_image(
            image_path,
            "Bypass Rate by Protection Type",
            "No bypass data available",
        )
    else:
        local_df = df.copy()
        if "protection_type" not in local_df.columns:
            local_df["protection_type"] = local_df["target"]
        local_df["bypass"] = pd.to_numeric(local_df["bypass"], errors="coerce").fillna(0)
        engines = local_df.groupby("engine")["bypass"].mean().sort_values(ascending=False).index.tolist()
        heatmap_data = pd.pivot_table(
            local_df, values="bypass", index="engine", columns="protection_type", aggfunc="mean", fill_value=0
        )
        if not heatmap_data.empty:
            heatmap_data = heatmap_data.reindex(engines).astype(float)

        n_rows = max(1, len(heatmap_data.index))
        n_cols = max(1, len(heatmap_data.columns))
        fig_w = max(12.0, 0.95 * n_cols + 8.0)
        fig_h = max(8.0, 0.42 * n_rows + 2.8)
        plt.figure(figsize=(fig_w, fig_h))

        show_annot = (n_rows * n_cols) <= 140
        y_font = 11 if n_rows <= 20 else 9 if n_rows <= 35 else 8

        sns.heatmap(
            heatmap_data,
            annot=show_annot,
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            fmt=".2f",
            linewidths=0.5,
            cbar_kws={"shrink": 0.9},
        )
        plt.title("Bypass Rate by Protection Type", fontsize=18)
        plt.xticks(rotation=90, ha="center", fontsize=11)
        plt.yticks(fontsize=y_font)
        # Reserve space for long engine labels and vertical protection labels.
        plt.subplots_adjust(left=0.45, bottom=0.32, right=0.97, top=0.92)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["bypass_protection_heatmap_image"] = image_path

    # Resource usage
    image_path = os.path.join(output_dir, report_settings.filenames.bypass_resource_usage)
    required_cols = {"engine", "avg_memory_mb", "avg_cpu_percent"}
    if df.empty or not required_cols.issubset(df.columns):
        images["bypass_resource_usage_image"] = _save_no_data_image(
            image_path,
            "Resource Usage (Normalized)",
            "No resource usage data available",
        )
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        resource_data = df.groupby("engine")[["avg_memory_mb", "avg_cpu_percent"]].mean().reset_index()
        resource_data = resource_data.sort_values("avg_memory_mb")
        x = np.arange(len(resource_data))
        width = 0.35
        max_memory = max(0.1, resource_data["avg_memory_mb"].max())
        max_cpu = max(0.1, resource_data["avg_cpu_percent"].max())
        memory_normalized = resource_data["avg_memory_mb"] / max_memory * 100
        cpu_normalized = resource_data["avg_cpu_percent"] / max_cpu * 100
        plt.bar(x - width / 2, memory_normalized, width, label="Memory", alpha=0.7, color="steelblue")
        plt.bar(x + width / 2, cpu_normalized, width, label="CPU", alpha=0.7, color="firebrick")
        plt.title("Resource Usage (Normalized)", fontsize=16)
        plt.ylabel("Usage (% of maximum)", fontsize=12)
        plt.xticks(x, resource_data["engine"].tolist(), rotation=45, ha="right", fontsize=10)
        plt.legend(loc="upper right")
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["bypass_resource_usage_image"] = image_path

    # Load time
    image_path = os.path.join(output_dir, report_settings.filenames.bypass_load_time)
    if df.empty or "engine" not in df.columns:
        images["bypass_load_time_image"] = _save_no_data_image(
            image_path,
            "Average Page Load Time by Browser",
            "No load time data available",
        )
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        local_df = df.copy()
        if "load_time_ms" not in local_df.columns and "load_time" in local_df.columns:
            local_df["load_time_ms"] = local_df["load_time"] * 1000
        elif "load_time_ms" not in local_df.columns:
            local_df["load_time_ms"] = 0
        load_time_by_engine = local_df.groupby("engine")["load_time_ms"].mean().reset_index().sort_values("load_time_ms")
        bars = sns.barplot(x="engine", y="load_time_ms", hue="engine", data=load_time_by_engine, palette="viridis", legend=False)
        for i, v in enumerate(load_time_by_engine["load_time_ms"]):
            bars.text(i, v + 50, f"{v:.0f} ms", ha="center", fontsize=10)
        plt.title("Average Page Load Time by Browser", fontsize=16)
        plt.ylabel("Load Time (ms)", fontsize=12)
        plt.xticks(rotation=45, ha="right", fontsize=10)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["bypass_load_time_image"] = image_path

    return images


def generate_timings_detailed_images(
        bypass_df: pd.DataFrame,
        browser_data_df: pd.DataFrame,
        output_dir: str
) -> Dict[str, str]:
    """Generate separate charts for each block of timings_dashboard."""

    images: Dict[str, str] = {}

    # Startup
    image_path = os.path.join(output_dir, report_settings.filenames.timing_startup)
    frames: list[pd.DataFrame] = []
    if not bypass_df.empty and {"engine", "startup_time_ms"}.issubset(bypass_df.columns):
        frames.append(bypass_df[["engine", "startup_time_ms"]].copy())
    if not browser_data_df.empty and {"engine", "startup_time_ms"}.issubset(browser_data_df.columns):
        frames.append(browser_data_df[["engine", "startup_time_ms"]].copy())
    if not frames:
        images["timing_startup_image"] = _save_no_data_image(image_path, "Browser Startup Time", "No startup timing data available")
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        startup_df = pd.concat(frames, ignore_index=True)
        startup_df["startup_time_ms"] = pd.to_numeric(startup_df["startup_time_ms"], errors="coerce")
        startup_df = startup_df.dropna(subset=["startup_time_ms"])
        startup_data = startup_df.groupby("engine")["startup_time_ms"].mean().reset_index().sort_values("startup_time_ms")
        sns.barplot(x="engine", y="startup_time_ms", hue="engine", data=startup_data, palette="viridis", legend=False)
        plt.title("Browser Startup Time", fontsize=16)
        plt.ylabel("ms", fontsize=12)
        plt.xticks(rotation=45, ha="right", fontsize=10)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["timing_startup_image"] = image_path

    # Bypass navigation vs full test
    image_path = os.path.join(output_dir, report_settings.filenames.timing_bypass)
    if bypass_df.empty or not {"engine", "load_time_ms", "test_duration_ms"}.issubset(bypass_df.columns):
        images["timing_bypass_image"] = _save_no_data_image(image_path, "Bypass: Navigation vs Full Test", "No bypass timing data available")
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        local_df = bypass_df.copy()
        local_df["load_time_ms"] = pd.to_numeric(local_df["load_time_ms"], errors="coerce")
        local_df["test_duration_ms"] = pd.to_numeric(local_df["test_duration_ms"], errors="coerce")
        local_df = local_df.dropna(subset=["load_time_ms", "test_duration_ms"])
        by_engine = local_df.groupby("engine")[["load_time_ms", "test_duration_ms"]].mean().reset_index().sort_values("test_duration_ms")
        x = np.arange(len(by_engine))
        width = 0.38
        plt.bar(x - width / 2, by_engine["load_time_ms"], width, label="Navigation", color="#4C78A8", alpha=0.9)
        plt.bar(x + width / 2, by_engine["test_duration_ms"], width, label="Full test", color="#F58518", alpha=0.85)
        plt.title("Bypass: Navigation vs Full Test", fontsize=16)
        plt.ylabel("ms", fontsize=12)
        plt.xticks(x, by_engine["engine"].tolist(), rotation=45, ha="right", fontsize=10)
        plt.legend(loc="upper left", fontsize=9)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["timing_bypass_image"] = image_path

    # Browser-data navigation vs full test
    image_path = os.path.join(output_dir, report_settings.filenames.timing_browser_data)
    required = {"engine", "navigation_time_ms", "test_duration_ms"}
    if browser_data_df.empty or not required.issubset(browser_data_df.columns):
        images["timing_browser_data_image"] = _save_no_data_image(
            image_path,
            "Browser Data: Navigation vs Full Test",
            "No browser-data timing data available",
        )
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        local_df = browser_data_df.copy()
        local_df["navigation_time_ms"] = pd.to_numeric(local_df["navigation_time_ms"], errors="coerce")
        local_df["test_duration_ms"] = pd.to_numeric(local_df["test_duration_ms"], errors="coerce")
        local_df = local_df.dropna(subset=["navigation_time_ms", "test_duration_ms"])
        by_engine = local_df.groupby("engine")[["navigation_time_ms", "test_duration_ms"]].mean().reset_index().sort_values("test_duration_ms")
        x = np.arange(len(by_engine))
        width = 0.38
        plt.bar(x - width / 2, by_engine["navigation_time_ms"], width, label="Navigation", color="#54A24B", alpha=0.9)
        plt.bar(x + width / 2, by_engine["test_duration_ms"], width, label="Full test", color="#E45756", alpha=0.85)
        plt.title("Browser Data: Navigation vs Full Test", fontsize=16)
        plt.ylabel("ms", fontsize=12)
        plt.xticks(x, by_engine["engine"].tolist(), rotation=45, ha="right", fontsize=10)
        plt.legend(loc="upper left", fontsize=9)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["timing_browser_data_image"] = image_path

    # Overhead
    image_path = os.path.join(output_dir, report_settings.filenames.timing_overhead)
    overhead_frames: list[pd.DataFrame] = []
    if not bypass_df.empty and {"engine", "load_time_ms", "test_duration_ms"}.issubset(bypass_df.columns):
        local_df = bypass_df.copy()
        local_df["load_time_ms"] = pd.to_numeric(local_df["load_time_ms"], errors="coerce")
        local_df["test_duration_ms"] = pd.to_numeric(local_df["test_duration_ms"], errors="coerce")
        local_df = local_df.dropna(subset=["load_time_ms", "test_duration_ms"])
        if not local_df.empty:
            local_df["overhead_ms"] = (local_df["test_duration_ms"] - local_df["load_time_ms"]).clip(lower=0)
            overhead_frames.append(local_df.groupby("engine", as_index=False)["overhead_ms"].mean().assign(source="bypass"))
    if not browser_data_df.empty and {"engine", "navigation_time_ms", "test_duration_ms"}.issubset(browser_data_df.columns):
        local_df = browser_data_df.copy()
        local_df["navigation_time_ms"] = pd.to_numeric(local_df["navigation_time_ms"], errors="coerce")
        local_df["test_duration_ms"] = pd.to_numeric(local_df["test_duration_ms"], errors="coerce")
        local_df = local_df.dropna(subset=["navigation_time_ms", "test_duration_ms"])
        if not local_df.empty:
            local_df["overhead_ms"] = (local_df["test_duration_ms"] - local_df["navigation_time_ms"]).clip(lower=0)
            overhead_frames.append(local_df.groupby("engine", as_index=False)["overhead_ms"].mean().assign(source="browser_data"))
    if not overhead_frames:
        images["timing_overhead_image"] = _save_no_data_image(
            image_path,
            "Timing Overhead (Full Test - Navigation)",
            "No overhead timing data available",
        )
    else:
        plt.figure(figsize=report_settings.visualization.figure_size_medium)
        overhead_df = pd.concat(overhead_frames, ignore_index=True)
        pivot_df = overhead_df.pivot_table(index="engine", columns="source", values="overhead_ms", aggfunc="mean").fillna(0)
        pivot_df["total"] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values("total").drop(columns=["total"])
        x = np.arange(len(pivot_df))
        width = 0.38
        bypass_values = pivot_df["bypass"] if "bypass" in pivot_df.columns else np.zeros(len(pivot_df))
        browser_values = pivot_df["browser_data"] if "browser_data" in pivot_df.columns else np.zeros(len(pivot_df))
        plt.bar(x - width / 2, bypass_values, width, label="Bypass overhead", color="#B279A2", alpha=0.9)
        plt.bar(x + width / 2, browser_values, width, label="Browser-data overhead", color="#72B7B2", alpha=0.9)
        plt.title("Timing Overhead (Full Test - Navigation)", fontsize=16)
        plt.ylabel("ms", fontsize=12)
        plt.xticks(x, pivot_df.index.tolist(), rotation=45, ha="right", fontsize=10)
        plt.legend(loc="upper left", fontsize=9)
        plt.grid(axis="y", **report_settings.colors.grid_style)
        plt.tight_layout()
        plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
        plt.close('all')
        images["timing_overhead_image"] = image_path

    return images


def generate_recaptcha_score_image(df: pd.DataFrame, output_dir: str) -> str:
    """
    Generate image for Recaptcha scores

    :param df: DataFrame containing recaptcha scores
    :param output_dir: Directory to save the generated image
    """

    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("Recaptcha Scores by Browser", fontsize=16)

    if df.empty or "recaptcha_score" not in df.columns:
        recaptcha_df = pd.DataFrame()
    else:
        recaptcha_df = df.dropna(subset=["recaptcha_score"])

    if recaptcha_df.empty:
        plt.text(0.5, 0.5, "No reCAPTCHA data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.recaptcha_scores)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    _create_recaptcha_plot(recaptcha_df)
    _add_recaptcha_note()

    image_path = os.path.join(output_dir, report_settings.filenames.recaptcha_scores)
    plt.tight_layout(rect=(0, 0.1, 1.0, 1.0))
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')

    return image_path


def generate_fingerprint_image(df: pd.DataFrame, output_dir: str) -> str:
    """
    Generate image for Fingerprint scores

    :param df: DataFrame containing Fingerprint scores
    :param output_dir: Directory to save the generated image
    """

    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("Fingerprint by Browser", fontsize=16)

    trust_col = _resolve_fingerprint_trust_column(df)
    if trust_col is None:
        fingerprint_df = pd.DataFrame()
    else:
        fingerprint_df = df.dropna(subset=[trust_col])

    if fingerprint_df.empty:
        plt.text(0.5, 0.5, "No Fingerprint data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.fingerprint_scores)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    _create_fingerprint_plot(fingerprint_df)
    _add_fingerprint_note()

    image_path = os.path.join(output_dir, report_settings.filenames.fingerprint_scores)
    plt.tight_layout(rect=(0, 0.04, 1.0, 1.0))
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')

    return image_path


def generate_fingerprint_demo_image(df: pd.DataFrame, output_dir: str) -> str:
    #https://fingerprint.com/demo/
    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("Fingerprint Demo by Browser", fontsize=16)

    target_df = _target_df(df, "fingerprint_demo")
    if target_df.empty:
        plt.text(0.5, 0.5, "No Fingerprint Demo data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.fingerprint_demo)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    if "suspect_score" not in target_df.columns:
        target_df["suspect_score"] = np.nan
    target_df["suspect_score"] = pd.to_numeric(target_df["suspect_score"], errors="coerce")
    score_data = target_df.groupby("engine")["suspect_score"].mean().reset_index()
    score_data = score_data.dropna(subset=["suspect_score"]).sort_values("suspect_score", ascending=False)

    if score_data.empty:
        plt.text(0.5, 0.5, "No suspect score data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.fingerprint_demo)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    sns.barplot(x="engine", y="suspect_score", hue="engine",
                data=score_data, palette="viridis", legend=False)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.ylabel("Suspect Score (%)", fontsize=12)
    plt.grid(axis="y", **report_settings.colors.grid_style)
    plt.figtext(0.5, 0.01, "Higher is worse", ha="center", fontsize=10)

    for i, v in enumerate(score_data["suspect_score"]):
        plt.text(i, v + 0.5, f"{v:.2f}", ha='center', va='bottom', fontsize=9)

    image_path = os.path.join(output_dir, report_settings.filenames.fingerprint_demo)
    plt.tight_layout()
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def generate_incolumitas_image(df: pd.DataFrame, output_dir: str) -> str:
    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("Incolumitas Payload Capture Rate by Browser", fontsize=16)

    target_df = _target_df(df, "incolumitas")
    if target_df.empty or "incolumitas_file" not in target_df.columns:
        plt.text(0.5, 0.5, "No Incolumitas data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.incolumitas)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    target_df["has_payload"] = target_df["incolumitas_file"].fillna("").astype(str).str.strip().ne("")
    coverage = target_df.groupby("engine")["has_payload"].mean().mul(100).reset_index()
    coverage = coverage.sort_values("has_payload", ascending=False)

    sns.barplot(x="engine", y="has_payload", hue="engine", data=coverage, palette="viridis", legend=False)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.ylabel("Payload Capture Rate (%)", fontsize=12)
    plt.ylim(0, 105)
    plt.grid(axis="y", **report_settings.colors.grid_style)

    for i, v in enumerate(coverage["has_payload"]):
        plt.text(i, v + 1.5, f"{v:.1f}%", ha='center', va='bottom', fontsize=9)

    image_path = os.path.join(output_dir, report_settings.filenames.incolumitas)
    plt.tight_layout()
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def generate_deviceandbrowserinfo_image(df: pd.DataFrame, output_dir: str) -> str:
    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("DeviceAndBrowserInfo Suspect Signals Rate", fontsize=16)

    target_df = _target_df(df, "deviceandbrowserinfo")
    if target_df.empty:
        plt.text(0.5, 0.5, "No DeviceAndBrowserInfo data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.deviceandbrowserinfo)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    if "deviceandbrowserinfo_file" in target_df.columns:
        target_df["suspect_signal_rate"] = target_df["deviceandbrowserinfo_file"].apply(
            _load_deviceandbrowserinfo_signal_ratio
        )
    else:
        target_df["suspect_signal_rate"] = np.nan

    # Fallback to precomputed metric when raw file path is unavailable.
    if "deviceandbrowserinfo_suspect_score" in target_df.columns:
        fallback_score = pd.to_numeric(target_df["deviceandbrowserinfo_suspect_score"], errors="coerce")
        target_df["suspect_signal_rate"] = target_df["suspect_signal_rate"].fillna(fallback_score)

    bot_rate = target_df.groupby("engine")["suspect_signal_rate"].mean().reset_index()
    bot_rate = bot_rate.dropna(subset=["suspect_signal_rate"]).sort_values("suspect_signal_rate", ascending=False)

    if bot_rate.empty:
        plt.text(0.5, 0.5, "No DeviceAndBrowserInfo signal data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.deviceandbrowserinfo)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    sns.barplot(x="engine", y="suspect_signal_rate", hue="engine", data=bot_rate, palette="viridis", legend=False)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.ylabel("True Signals / All Signals (%)", fontsize=12)
    plt.ylim(0, 105)
    plt.grid(axis="y", **report_settings.colors.grid_style)

    for i, v in enumerate(bot_rate["suspect_signal_rate"]):
        plt.text(i, v + 1.5, f"{v:.1f}%", ha='center', va='bottom', fontsize=9)

    image_path = os.path.join(output_dir, report_settings.filenames.deviceandbrowserinfo)
    plt.tight_layout()
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def generate_scan_fingerprint_image(df: pd.DataFrame, output_dir: str) -> str:
    plt.figure(figsize=report_settings.visualization.figure_size_medium)
    plt.title("Fingerprint Scan Bot Risk Score by Browser", fontsize=16)

    target_df = _target_df(df, "scan_fingerprint")
    if target_df.empty or "scan_fingerprint_bot_risk_score" not in target_df.columns:
        plt.text(0.5, 0.5, "No Fingerprint Scan data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.scan_fingerprint)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    target_df["scan_fingerprint_bot_risk_score"] = pd.to_numeric(
        target_df["scan_fingerprint_bot_risk_score"], errors="coerce"
    )
    score_data = target_df.groupby("engine")["scan_fingerprint_bot_risk_score"].mean().reset_index()
    score_data = score_data.dropna(subset=["scan_fingerprint_bot_risk_score"]).sort_values(
        "scan_fingerprint_bot_risk_score", ascending=True
    )

    if score_data.empty:
        plt.text(0.5, 0.5, "No Fingerprint Scan bot risk score data available",
                 ha='center', va='center', fontsize=16)
        image_path = os.path.join(output_dir, report_settings.filenames.scan_fingerprint)
        plt.savefig(image_path, dpi=report_settings.visualization.dpi)
        plt.close('all')
        return image_path

    sns.barplot(x="engine", y="scan_fingerprint_bot_risk_score", hue="engine",
                data=score_data, palette="viridis", legend=False)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.ylabel("Bot Risk Score (0-100, lower is better)", fontsize=12)
    plt.ylim(0, 105)
    plt.grid(axis="y", **report_settings.colors.grid_style)
    plt.axhline(y=30, color='green', linestyle='--', alpha=0.5, label="Lower Risk Zone")
    plt.axhline(y=70, color='red', linestyle='--', alpha=0.5, label="Higher Risk Zone")
    plt.legend(loc="upper right", fontsize=9)

    for i, v in enumerate(score_data["scan_fingerprint_bot_risk_score"]):
        plt.text(i, v + 1.5, f"{v:.1f}", ha='center', va='bottom', fontsize=9)

    image_path = os.path.join(output_dir, report_settings.filenames.scan_fingerprint)
    plt.tight_layout()
    plt.savefig(image_path, dpi=report_settings.visualization.dpi, bbox_inches="tight")
    plt.close('all')
    return image_path


def _create_bypass_rate_subplot(df: pd.DataFrame, engine_colors: Dict[str, Any]) -> None:
    """
    Create the bypass rate subplot (top left)

    :param df: DataFrame containing bypass benchmark results
    :param engine_colors: Dictionary mapping engines to their colors
    """

    plt.subplot(2, 2, 1)
    bypass_by_engine = df.groupby("engine")["bypass"].mean().reset_index()
    bypass_by_engine["bypass_percent"] = bypass_by_engine["bypass"] * 100
    bypass_by_engine = bypass_by_engine.sort_values("bypass_percent", ascending=False)

    bars = plt.bar(bypass_by_engine["engine"], bypass_by_engine["bypass_percent"],
                   color=[engine_colors[e] for e in bypass_by_engine["engine"]])

    # value labels on bars
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2., height + 1,
                 f'{height:.1f}%', ha='center', va='bottom', fontsize=9)

    plt.title("Bypass Rate by Browser", fontsize=16)
    plt.ylabel("Bypass Rate (%)", fontsize=12)
    plt.ylim(0, max(1, max(bypass_by_engine["bypass_percent"])) * 1.15)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.grid(axis="y", **report_settings.colors.grid_style)


def _create_protection_heatmap_subplot(df: pd.DataFrame, engines: List[str]) -> None:
    """
    Create the protection type heatmap subplot (top right)

    :param df: DataFrame containing bypass benchmark results
    :param engines: List of engine names to order the heatmap
    """

    plt.subplot(2, 2, 2)

    if "protection_type" not in df.columns:
        df = df.copy()
        df["protection_type"] = df["target"]

    # ensure bypass column is a number
    df["bypass"] = pd.to_numeric(df["bypass"], errors="coerce").fillna(0)

    heatmap_data = pd.pivot_table(
        df, values="bypass",
        index="engine", columns="protection_type",
        aggfunc="mean",
        fill_value=0
    )

    if not heatmap_data.empty:
        heatmap_data = heatmap_data.reindex(engines)
        heatmap_data = heatmap_data.astype(float)

    n_rows = len(heatmap_data.index)
    n_cols = len(heatmap_data.columns)
    show_annot = (n_rows * n_cols) <= 120

    sns.heatmap(
        heatmap_data,
        annot=show_annot,
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        fmt=".2f",
        linewidths=0.5,
        cbar_kws={"shrink": 0.8},
    )
    plt.title("Bypass Rate by Protection Type", fontsize=16)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.yticks(fontsize=8)
    plt.tight_layout()


def _create_resource_usage_subplot(df: pd.DataFrame) -> None:
    """
    Create the resource usage subplot (bottom left)

    :param df: DataFrame containing bypass benchmark results
    """

    plt.subplot(2, 2, 3)

    # prepare data
    resource_data = df.groupby("engine")[["avg_memory_mb", "avg_cpu_percent"]].mean().reset_index()
    resource_data = resource_data.sort_values("avg_memory_mb")

    # grouped bars for memory and CPU
    x = np.arange(len(resource_data))
    width = 0.35

    # normalize values to make them comparable on same scale
    max_memory = max(0.1, resource_data["avg_memory_mb"].max())
    max_cpu = max(0.1, resource_data["avg_cpu_percent"].max())
    resource_data["memory_normalized"] = resource_data["avg_memory_mb"] / max_memory * 100
    resource_data["cpu_normalized"] = resource_data["avg_cpu_percent"] / max_cpu * 100

    bar1 = plt.bar(x - width / 2, resource_data["memory_normalized"], width,
                   label="Memory", alpha=0.7, color="steelblue")
    bar2 = plt.bar(x + width / 2, resource_data["cpu_normalized"], width,
                   label="CPU", alpha=0.7, color="firebrick")

    # annotations
    for i, bars in enumerate(zip(bar1, bar2)):
        for j, bar in enumerate(bars):
            value = resource_data.iloc[i]["avg_memory_mb"] if j == 0 else resource_data.iloc[i]["avg_cpu_percent"]
            unit = "MB" if j == 0 else "%"
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                     f'{value:.1f}{unit}', ha='center', va='bottom', fontsize=8)

    plt.title("Resource Usage (Normalized)", fontsize=16)
    plt.ylabel("Usage (% of maximum)", fontsize=12)
    plt.xticks(x, resource_data["engine"].tolist(), rotation=45, ha="right", fontsize=10)
    plt.legend(loc="upper right")
    plt.grid(axis="y", **report_settings.colors.grid_style)
    plt.ylim(0, 120)


def _create_load_time_subplot(df: pd.DataFrame) -> None:
    """
    Create the load time subplot (bottom right)

    :param df: DataFrame containing bypass benchmark results
    """

    plt.subplot(2, 2, 4)

    if "load_time_ms" not in df.columns and "load_time" in df.columns:
        df = df.copy()
        df["load_time_ms"] = df["load_time"] * 1000
    elif "load_time_ms" not in df.columns:
        df = df.copy()
        df["load_time_ms"] = 0

    # average page load time by engine
    load_time_by_engine = df.groupby("engine")["load_time_ms"].mean().reset_index()
    load_time_by_engine = load_time_by_engine.sort_values("load_time_ms")

    bar_plot = sns.barplot(x="engine", y="load_time_ms", hue="engine",
                           data=load_time_by_engine, palette="viridis", legend=False)

    plt.title("Average Page Load Time by Browser", fontsize=16)
    plt.xlabel("Browser", fontsize=12)
    plt.ylabel("Load Time (ms)", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.7)

    # value labels on bars
    for i, v in enumerate(load_time_by_engine["load_time_ms"]):
        bar_plot.text(i, v + 50, f"{v:.0f} ms", ha="center", fontsize=10)


def _draw_no_data_subplot(title: str, message: str) -> None:
    plt.title(title, fontsize=16)
    plt.text(0.5, 0.5, message, ha='center', va='center', fontsize=12)
    plt.xticks([])
    plt.yticks([])


def _create_startup_timing_subplot(bypass_df: pd.DataFrame, browser_data_df: pd.DataFrame) -> None:
    plt.subplot(2, 2, 1)

    frames: list[pd.DataFrame] = []
    if not bypass_df.empty and {"engine", "startup_time_ms"}.issubset(bypass_df.columns):
        frames.append(bypass_df[["engine", "startup_time_ms"]].copy())
    if not browser_data_df.empty and {"engine", "startup_time_ms"}.issubset(browser_data_df.columns):
        frames.append(browser_data_df[["engine", "startup_time_ms"]].copy())

    if not frames:
        _draw_no_data_subplot("Startup Time", "No startup timing data available")
        return

    startup_df = pd.concat(frames, ignore_index=True)
    startup_df["startup_time_ms"] = pd.to_numeric(startup_df["startup_time_ms"], errors="coerce")
    startup_df = startup_df.dropna(subset=["startup_time_ms"])
    if startup_df.empty:
        _draw_no_data_subplot("Startup Time", "No startup timing data available")
        return

    startup_data = startup_df.groupby("engine")["startup_time_ms"].mean().reset_index()
    startup_data = startup_data.sort_values("startup_time_ms")

    sns.barplot(x="engine", y="startup_time_ms", hue="engine", data=startup_data, palette="viridis", legend=False)
    plt.title("Browser Startup Time", fontsize=16)
    plt.ylabel("ms", fontsize=12)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.grid(axis="y", **report_settings.colors.grid_style)


def _create_bypass_timing_subplot(bypass_df: pd.DataFrame) -> None:
    plt.subplot(2, 2, 2)

    if bypass_df.empty or "engine" not in bypass_df.columns:
        _draw_no_data_subplot("Bypass Timings", "No bypass timing data available")
        return

    local_df = bypass_df.copy()
    local_df["load_time_ms"] = pd.to_numeric(local_df.get("load_time_ms"), errors="coerce")
    local_df["test_duration_ms"] = pd.to_numeric(local_df.get("test_duration_ms"), errors="coerce")
    local_df = local_df.dropna(subset=["load_time_ms", "test_duration_ms"])
    if local_df.empty:
        _draw_no_data_subplot("Bypass Timings", "No bypass timing data available")
        return

    by_engine = local_df.groupby("engine")[["load_time_ms", "test_duration_ms"]].mean().reset_index()
    by_engine = by_engine.sort_values("test_duration_ms")

    x = np.arange(len(by_engine))
    width = 0.38
    plt.bar(x - width / 2, by_engine["load_time_ms"], width, label="Navigation", color="#4C78A8", alpha=0.9)
    plt.bar(x + width / 2, by_engine["test_duration_ms"], width, label="Full test", color="#F58518", alpha=0.85)

    plt.title("Bypass: Navigation vs Full Test", fontsize=16)
    plt.ylabel("ms", fontsize=12)
    plt.xticks(x, by_engine["engine"].tolist(), rotation=45, ha="right", fontsize=10)
    plt.legend(loc="upper left", fontsize=9)
    plt.grid(axis="y", **report_settings.colors.grid_style)


def _create_browser_data_timing_subplot(browser_data_df: pd.DataFrame) -> None:
    plt.subplot(2, 2, 3)

    required = {"engine", "navigation_time_ms", "test_duration_ms"}
    if browser_data_df.empty or not required.issubset(browser_data_df.columns):
        _draw_no_data_subplot("Browser Data Timings", "No browser-data timing data available")
        return

    local_df = browser_data_df.copy()
    local_df["navigation_time_ms"] = pd.to_numeric(local_df["navigation_time_ms"], errors="coerce")
    local_df["test_duration_ms"] = pd.to_numeric(local_df["test_duration_ms"], errors="coerce")
    local_df = local_df.dropna(subset=["navigation_time_ms", "test_duration_ms"])
    if local_df.empty:
        _draw_no_data_subplot("Browser Data Timings", "No browser-data timing data available")
        return

    by_engine = local_df.groupby("engine")[["navigation_time_ms", "test_duration_ms"]].mean().reset_index()
    by_engine = by_engine.sort_values("test_duration_ms")

    x = np.arange(len(by_engine))
    width = 0.38
    plt.bar(x - width / 2, by_engine["navigation_time_ms"], width, label="Navigation", color="#54A24B", alpha=0.9)
    plt.bar(x + width / 2, by_engine["test_duration_ms"], width, label="Full test", color="#E45756", alpha=0.85)

    plt.title("Browser Data: Navigation vs Full Test", fontsize=16)
    plt.ylabel("ms", fontsize=12)
    plt.xticks(x, by_engine["engine"].tolist(), rotation=45, ha="right", fontsize=10)
    plt.legend(loc="upper left", fontsize=9)
    plt.grid(axis="y", **report_settings.colors.grid_style)


def _create_overhead_timing_subplot(bypass_df: pd.DataFrame, browser_data_df: pd.DataFrame) -> None:
    plt.subplot(2, 2, 4)

    overhead_frames: list[pd.DataFrame] = []

    if not bypass_df.empty and {"engine", "load_time_ms", "test_duration_ms"}.issubset(bypass_df.columns):
        bypass_local = bypass_df.copy()
        bypass_local["load_time_ms"] = pd.to_numeric(bypass_local["load_time_ms"], errors="coerce")
        bypass_local["test_duration_ms"] = pd.to_numeric(bypass_local["test_duration_ms"], errors="coerce")
        bypass_local = bypass_local.dropna(subset=["load_time_ms", "test_duration_ms"])
        if not bypass_local.empty:
            bypass_local["overhead_ms"] = (bypass_local["test_duration_ms"] - bypass_local["load_time_ms"]).clip(lower=0)
            overhead_frames.append(
                bypass_local.groupby("engine", as_index=False)["overhead_ms"].mean().assign(source="bypass")
            )

    if not browser_data_df.empty and {"engine", "navigation_time_ms", "test_duration_ms"}.issubset(browser_data_df.columns):
        browser_local = browser_data_df.copy()
        browser_local["navigation_time_ms"] = pd.to_numeric(browser_local["navigation_time_ms"], errors="coerce")
        browser_local["test_duration_ms"] = pd.to_numeric(browser_local["test_duration_ms"], errors="coerce")
        browser_local = browser_local.dropna(subset=["navigation_time_ms", "test_duration_ms"])
        if not browser_local.empty:
            browser_local["overhead_ms"] = (
                browser_local["test_duration_ms"] - browser_local["navigation_time_ms"]
            ).clip(lower=0)
            overhead_frames.append(
                browser_local.groupby("engine", as_index=False)["overhead_ms"].mean().assign(source="browser_data")
            )

    if not overhead_frames:
        _draw_no_data_subplot("Timing Overhead", "No overhead timing data available")
        return

    overhead_df = pd.concat(overhead_frames, ignore_index=True)
    pivot_df = overhead_df.pivot_table(index="engine", columns="source", values="overhead_ms", aggfunc="mean").fillna(0)
    pivot_df["total"] = pivot_df.sum(axis=1)
    pivot_df = pivot_df.sort_values("total").drop(columns=["total"])

    x = np.arange(len(pivot_df))
    width = 0.38
    bypass_values = pivot_df["bypass"] if "bypass" in pivot_df.columns else np.zeros(len(pivot_df))
    browser_values = pivot_df["browser_data"] if "browser_data" in pivot_df.columns else np.zeros(len(pivot_df))

    plt.bar(x - width / 2, bypass_values, width, label="Bypass overhead", color="#B279A2", alpha=0.9)
    plt.bar(x + width / 2, browser_values, width, label="Browser-data overhead", color="#72B7B2", alpha=0.9)

    plt.title("Timing Overhead (Full Test - Navigation)", fontsize=16)
    plt.ylabel("ms", fontsize=12)
    plt.xticks(x, pivot_df.index.tolist(), rotation=45, ha="right", fontsize=10)
    plt.legend(loc="upper left", fontsize=9)
    plt.grid(axis="y", **report_settings.colors.grid_style)


def _create_recaptcha_plot(recaptcha_df: pd.DataFrame) -> None:
    """
    Create the reCAPTCHA scores plot

    :param recaptcha_df: DataFrame containing reCAPTCHA scores
    """

    recaptcha_data = recaptcha_df.groupby("engine")["recaptcha_score"].mean().reset_index()
    recaptcha_data = recaptcha_data.sort_values("recaptcha_score", ascending=False)

    sns.barplot(x="engine", y="recaptcha_score", hue="engine",
                data=recaptcha_data, palette="viridis", legend=False)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    plt.ylabel("Recaptcha Score (0-1)", fontsize=12)
    plt.ylim(0, 1.05)

    # reference lines for good scores
    plt.axhline(y=report_settings.thresholds.highlight_good_score, color='green', linestyle='--',
                alpha=0.5, label="Good Score (0.8+)")
    plt.axhline(y=report_settings.thresholds.highlight_bad_score, color='red', linestyle='--',
                alpha=0.5, label="Bad Score (0.2-)")

    plt.legend(loc="upper right", fontsize=9)
    plt.grid(axis="y", **report_settings.colors.grid_style)

    # value annotations
    for i, v in enumerate(recaptcha_data["recaptcha_score"]):
        plt.text(i, v + 0.02, f'{v:.2f}', ha='center', va='bottom', fontsize=9)


def _create_fingerprint_plot(fingerprint_df: pd.DataFrame) -> None:
    """
    Create the Fingerprint scores plot

    :param fingerprint_df: DataFrame containing Fingerprint scores
    """

    trust_col = _resolve_fingerprint_trust_column(fingerprint_df)
    if trust_col is None:
        return
    suspect_col = _resolve_fingerprint_suspect_column(fingerprint_df)
    if suspect_col is None:
        fingerprint_df = fingerprint_df.copy()
        fingerprint_df["suspect_score"] = np.nan
        suspect_col = "suspect_score"

    fingerprint_data = fingerprint_df.groupby("engine")[[trust_col, suspect_col]].mean().reset_index()
    fingerprint_data = fingerprint_data.sort_values(trust_col, ascending=False)

    x = np.arange(len(fingerprint_data))
    width = 0.35

    bar1 = plt.bar(x - width / 2, fingerprint_data[trust_col], width,
                   label="Trust Score (higher is better)", color=report_settings.colors.success)
    bar2 = plt.bar(x + width / 2, fingerprint_data[suspect_col], width,
                   label="Suspect Score (lower is better)", color=report_settings.colors.failure)

    plt.xticks(x, fingerprint_data["engine"].tolist(), rotation=45, ha="right", fontsize=10)
    plt.ylabel("Score (0-100%)", fontsize=12)
    plt.ylim(0, 105)

    # reference lines for good scores
    plt.axhline(y=report_settings.thresholds.fingerprint_good_trust_score, color='green', linestyle='--',
                alpha=0.5, label="Good Trust Score")
    plt.axhline(y=report_settings.thresholds.fingerprint_good_bot_score, color='red', linestyle='--',
                alpha=0.5, label="Good Bot Score")

    plt.legend(loc="upper right", fontsize=9)
    plt.grid(axis="y", **report_settings.colors.grid_style)

    # Value annotations
    for i, bars in enumerate(zip(bar1, bar2)):
        for j, bar in enumerate(bars):
            value = fingerprint_data.iloc[i][trust_col] if j == 0 else fingerprint_data.iloc[i][suspect_col]
            plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                     f'{value}%', ha='center', va='bottom', fontsize=9)


def _add_dashboard_note() -> None:
    """Add explanatory note to dashboard"""

    ax = plt.axes((0.40, 0.01, 0.2, 0.02), frameon=False)
    ax.text(0.5, 0.5, 'Lower values are better for resource usage and load time',
            ha='center', va='center', fontsize=10, style='italic')
    ax.set_xticks([])
    ax.set_yticks([])


def _add_recaptcha_note() -> None:
    """Explanatory note for reCAPTCHA plot"""

    plt.figtext(0.5, 0.01,
                "The Score shows if Google considers you as HUMAN or BOT: 1.0 - human, 0.0 - bot\n"
                "With score < 0.3 you'll get a slow reCAPTCHA 2, it would be hard to solve it.\n"
                "with score >= 0.7 it will be much easier.",
                ha='center', fontsize=10, style='italic')


def _add_fingerprint_note() -> None:
    """Explanatory note for Fingerprint plot"""

    plt.figtext(0.5, 0.01,
                "Higher trust score = better fingerprinting protection\nLower suspect score = less bot-like behavior",
                ha='center', fontsize=10, style='italic')
