from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single test run"""

    load_time_ms: int = 0
    test_duration_ms: int = 0
    memory_mb: int = 0
    cpu_percent: float = 0.0
    peak_rss_mb: int = 0
    max_cpu_percent: float = 0.0


@dataclass
class MetricSummary:
    """Summary statistics for a numeric metric."""

    min: float = 0.0
    mean: float = 0.0
    max: float = 0.0


@dataclass
class BypassTestResult:
    """Result of a bypass test"""

    target: str
    url: str
    bypass: bool = False
    error: Optional[str] = None
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)


@dataclass
class BrowserDataResult:
    """Result of browser data extraction"""

    target: str
    url: str
    error: Optional[str] = None
    navigation_time_ms: int = 0
    test_duration_ms: int = 0
    # Fingerprint data
    fingerprint_untrust_score: Optional[float] = None
    suspect_score: Optional[float] = None
    fingerprint_webrtc_ip: Optional[str] = None
    # fingerprint.com demo raw payload file
    fingerprint_demo_file: Optional[str] = None
    # recaptcha data
    recaptcha_score: Optional[float] = None
    # IP data
    ip: Optional[str] = None
    # incolumitas payload file
    incolumitas_file: Optional[str] = None
    # deviceandbrowserinfo results
    deviceandbrowserinfo_is_bot: Optional[bool] = None
    deviceandbrowserinfo_file: Optional[str] = None
    deviceandbrowserinfo_suspect_score: Optional[float] = None
    # fingerprint-scan score
    scan_fingerprint_bot_risk_score: Optional[int] = None


@dataclass
class BenchmarkResults:
    """Complete benchmark results for an engine"""
    
    engine: str
    timestamp: str
    bypass_targets_results: List[BypassTestResult] = field(default_factory=list)
    browser_data_targets_results: List[BrowserDataResult] = field(default_factory=list)
    startup_time_ms: Optional[int] = None
    average_memory_mb: int = 0
    average_cpu_percent: float = 0.0
    memory_mb_stats: MetricSummary = field(default_factory=MetricSummary)
    cpu_percent_stats: MetricSummary = field(default_factory=MetricSummary)
    peak_rss_mb_stats: MetricSummary = field(default_factory=MetricSummary)
    max_cpu_percent_stats: MetricSummary = field(default_factory=MetricSummary)
    bypass_rate: float = 0.0
    error: Optional[str] = None
