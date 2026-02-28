from typing import List, Sequence

from utils.dataclasses import BypassTestResult


def calculate_metrics(
        bypass_results: List[BypassTestResult],
        memory_readings: List[int],
        cpu_readings: List[float]
) -> tuple[int, float, float]:
    """
    Calculate average metrics from test results

    :param bypass_results: List of BypassTestResult objects containing bypass test results
    :param memory_readings: List of memory usage readings in MB
    :param cpu_readings: List of CPU usage readings in percentage
    :return: Tuple containing average memory usage (MB), average CPU usage (percentage), and bypass rate
    """

    avg_memory = int(sum(memory_readings) / len(memory_readings)) if memory_readings else 0
    avg_cpu = sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0.0

    bypass_count = sum(1 for r in bypass_results if r.bypass and not r.error)
    bypass_rate = bypass_count / len(bypass_results) if bypass_results else 0.0

    return avg_memory, avg_cpu, bypass_rate


def calculate_min_mean_max(readings: Sequence[float]) -> tuple[float, float, float]:
    """
    Calculate min/mean/max for a sequence of numeric readings.

    :param readings: Sequence of numeric values
    :return: (min, mean, max); zeros for empty input
    """
    if not readings:
        return 0.0, 0.0, 0.0

    minimum = min(readings)
    maximum = max(readings)
    mean = sum(readings) / len(readings)
    return minimum, mean, maximum
