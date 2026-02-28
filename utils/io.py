import fcntl
import json
import os

from config.settings import settings
from utils.dataclasses import BenchmarkResults


def create_directory_structure(timestamp: str) -> tuple[str, str, str]:
    """
    Create the necessary directory structure for results

    :param timestamp: Timestamp to create unique directory names
    :return: Tuple containing paths to result directory, media directory, and screenshots directory
    """

    result_path = os.path.join(settings.paths.results_path, timestamp)
    media_path = os.path.join(result_path, settings.paths.media_dir)
    screenshots_path = os.path.join(media_path, settings.paths.screenshots_dir)

    directories = [
        settings.paths.results_path,
        result_path,
        media_path,
        screenshots_path,
        settings.paths.binaries_path,
        settings.paths.profiles_path
    ]

    for directory in directories:
        os.makedirs(directory, exist_ok=True)

    return result_path, media_path, screenshots_path


def save_results(results: BenchmarkResults, result_path: str) -> str:
    """Save results to `benchmark_results.json`, replacing old entry for the same engine."""

    results_file = os.path.join(result_path, f"benchmark_results.json")

    # Convert dataclasses to dict for JSON serialization
    results_dict = {
        "engine": results.engine,
        "timestamp": results.timestamp,
        "bypass_targets_results": [
            {
                "target": r.target,
                "url": r.url,
                "bypass": r.bypass,
                "error": r.error,
                "load_time_ms": r.performance.load_time_ms,
                "memory_mb": r.performance.memory_mb,
                "cpu_percent": r.performance.cpu_percent,
                "peak_rss_mb": r.performance.peak_rss_mb,
                "max_cpu_percent": r.performance.max_cpu_percent,
            } for r in results.bypass_targets_results
        ],
        "browser_data_targets_results": [
            {
                "target": r.target,
                "url": r.url,
                "error": r.error,
                "fingerprint_untrust_score": r.fingerprint_untrust_score,
                "suspect_score": r.suspect_score,
                "fingerprint_webrtc_ip": r.fingerprint_webrtc_ip,
                "fingerprint_demo_file": r.fingerprint_demo_file,
                "recaptcha_score": r.recaptcha_score,
                "ip": r.ip,
                "incolumitas_file": r.incolumitas_file,
                "deviceandbrowserinfo_is_bot": r.deviceandbrowserinfo_is_bot,
                "deviceandbrowserinfo_file": r.deviceandbrowserinfo_file,
                "deviceandbrowserinfo_suspect_score": r.deviceandbrowserinfo_suspect_score,
                "scan_fingerprint_bot_risk_score": r.scan_fingerprint_bot_risk_score
            } for r in results.browser_data_targets_results
        ],
        "average_memory_mb": results.average_memory_mb,
        "average_cpu_percent": results.average_cpu_percent,
        "bypass_rate": results.bypass_rate,
        "error": results.error
    }

    with open(results_file, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip()
            try:
                existing_results = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                existing_results = []

            # Keep one fresh record per engine.
            existing_results = [r for r in existing_results if r.get("engine") != results.engine]
            all_results = existing_results + [results_dict]

            f.seek(0)
            f.truncate()
            json.dump(all_results, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return results_file
