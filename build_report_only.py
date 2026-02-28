import argparse
import logging
import time
from pathlib import Path

from utils.report import generate_report
from utils.logging.logging import setup_logging

logger = logging.getLogger(__name__)


def _find_latest_results_dir(results_root: Path) -> Path:
    candidates = []
    if not results_root.exists():
        raise FileNotFoundError(f"Results directory does not exist: {results_root}")

    for child in results_root.iterdir():
        if not child.is_dir():
            continue
        results_file = child / "benchmark_results.json"
        if results_file.exists():
            candidates.append((results_file.stat().st_mtime, child))

    if not candidates:
        raise FileNotFoundError(
            f"No benchmark run folder with benchmark_results.json found in {results_root}"
        )

    return max(candidates, key=lambda item: item[0])[1]


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.results_file:
        results_file = Path(args.results_file).expanduser().resolve()
        output_dir = results_file.parent
        return results_file, output_dir

    if args.results_dir:
        output_dir = Path(args.results_dir).expanduser().resolve()
    else:
        output_dir = _find_latest_results_dir(Path(args.results_root).expanduser().resolve())

    return output_dir / "benchmark_results.json", output_dir


def _build_once(results_file: Path, output_dir: Path) -> None:
    if not results_file.exists():
        raise FileNotFoundError(f"Results JSON not found: {results_file}")
    generate_report(str(results_file), str(output_dir))
    logger.info("Report refreshed from %s", results_file)


def _watch(results_file: Path, output_dir: Path, interval: float) -> None:
    logger.info("Watch mode enabled: %s (interval %.1fs)", results_file, interval)
    last_signature = None

    while True:
        if results_file.exists():
            st = results_file.stat()
            signature = (st.st_mtime_ns, st.st_size)
            if signature != last_signature:
                _build_once(results_file, output_dir)
                last_signature = signature
        else:
            logger.warning("Results JSON not found yet: %s", results_file)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build summary report from benchmark_results.json without running benchmarks."
    )
    parser.add_argument(
        "--results-file",
        help="Path to benchmark_results.json. If provided, has highest priority.",
    )
    parser.add_argument(
        "--results-dir",
        help="Path to a specific run directory (contains benchmark_results.json).",
    )
    parser.add_argument(
        "--results-root",
        default="results",
        help="Root results directory used to auto-pick latest run if no path args are provided.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and rebuild report whenever benchmark_results.json changes.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Polling interval in seconds for --watch mode.",
    )
    args = parser.parse_args()

    setup_logging(engine_name="report-only")
    results_file, output_dir = _resolve_paths(args)
    logger.info("Using run directory: %s", output_dir)

    if args.watch:
        try:
            _watch(results_file, output_dir, max(0.5, args.interval))
        except KeyboardInterrupt:
            logger.info("Watch stopped by user")
    else:
        _build_once(results_file, output_dir)


if __name__ == "__main__":
    main()
