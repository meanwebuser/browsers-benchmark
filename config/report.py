"""
Configuration settings for report generation using pydantic.
"""

from typing import Any, Dict, Tuple

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class VisualizationSettings(BaseModel):
    """Configuration settings for visualization"""

    figure_size_large: Tuple[int, int] = (20, 16)
    figure_size_medium: Tuple[int, int] = (12, 8)
    dpi: int = 300

    model_config = {"extra": "ignore"}


class ColorSettings(BaseModel):
    """Configuration settings for color schemes"""

    success: str = "forestgreen"
    failure: str = "firebrick"
    grid_linestyle: str = "--"
    grid_alpha: float = 0.3

    @property
    def score(self) -> Dict[str, str]:
        """Return score colors as dictionary"""

        return {
            "success": self.success,
            "failure": self.failure,
        }

    @property
    def grid_style(self) -> Dict[str, Any]:
        """Return grid styling as dictionary"""

        return {
            "linestyle": self.grid_linestyle,
            "alpha": self.grid_alpha
        }

    model_config = {"extra": "ignore"}


class ScoreThresholds(BaseModel):
    """Configuration settings for score thresholds"""

    highlight_good_score: float = 0.8
    highlight_bad_score: float = 0.2
    fingerprint_good_trust_score: float = 80.0
    fingerprint_good_bot_score: float = 20.0

    model_config = {"extra": "ignore"}


class FilenameSettings(BaseModel):
    """Configuration settings for output filenames"""

    bypass_dashboard: str = "bypass_dashboard.png"
    bypass_rate: str = "bypass_rate.png"
    bypass_protection_heatmap: str = "bypass_protection_heatmap.png"
    bypass_resource_usage: str = "bypass_resource_usage.png"
    bypass_load_time: str = "bypass_load_time.png"
    timings_dashboard: str = "timings_dashboard.png"
    timing_startup: str = "timing_startup.png"
    timing_bypass: str = "timing_bypass.png"
    timing_browser_data: str = "timing_browser_data.png"
    timing_overhead: str = "timing_overhead.png"
    recaptcha_scores: str = "recaptcha_scores.png"
    fingerprint_scores: str = "fingerprint_scores.png"
    fingerprint_demo: str = "fingerprint_demo.png"
    incolumitas: str = "incolumitas.png"
    deviceandbrowserinfo: str = "deviceandbrowserinfo.png"
    scan_fingerprint: str = "scan_fingerprint.png"
    summary: str = "summary.md"

    model_config = {"extra": "ignore"}


class ReportSettings(BaseSettings):
    """Report configuration settings"""

    # visualization settings
    FIGURE_SIZE_LARGE_WIDTH: int = 20
    FIGURE_SIZE_LARGE_HEIGHT: int = 16
    FIGURE_SIZE_MEDIUM_WIDTH: int = 12
    FIGURE_SIZE_MEDIUM_HEIGHT: int = 8
    DPI: int = 300

    # color settings
    SUCCESS_COLOR: str = "forestgreen"
    FAILURE_COLOR: str = "firebrick"
    GRID_LINESTYLE: str = "--"
    GRID_ALPHA: float = 0.3

    # score thresholds
    HIGHLIGHT_GOOD_SCORE: float = 0.8
    HIGHLIGHT_BAD_SCORE: float = 0.2
    FINGERPRINT_GOOD_TRUST_SCORE: float = 80.0
    FINGERPRINT_GOOD_BOT_SCORE: float = 20.0

    # output filenames
    BYPASS_DASHBOARD_FILENAME: str = "bypass_dashboard.png"
    BYPASS_RATE_FILENAME: str = "bypass_rate.png"
    BYPASS_PROTECTION_HEATMAP_FILENAME: str = "bypass_protection_heatmap.png"
    BYPASS_RESOURCE_USAGE_FILENAME: str = "bypass_resource_usage.png"
    BYPASS_LOAD_TIME_FILENAME: str = "bypass_load_time.png"
    TIMINGS_DASHBOARD_FILENAME: str = "timings_dashboard.png"
    TIMING_STARTUP_FILENAME: str = "timing_startup.png"
    TIMING_BYPASS_FILENAME: str = "timing_bypass.png"
    TIMING_BROWSER_DATA_FILENAME: str = "timing_browser_data.png"
    TIMING_OVERHEAD_FILENAME: str = "timing_overhead.png"
    RECAPTCHA_SCORES_FILENAME: str = "recaptcha_scores.png"
    FINGERPRINT_SCORES_FILENAME: str = "fingerprint_scores.png"
    FINGERPRINT_DEMO_FILENAME: str = "fingerprint_demo.png"
    INCOLUMITAS_FILENAME: str = "incolumitas.png"
    DEVICEANDBROWSERINFO_FILENAME: str = "deviceandbrowserinfo.png"
    scan_fingerprint_FILENAME: str = "scan_fingerprint.png"
    SUMMARY_FILENAME: str = "summary.md"

    @property
    def visualization(self) -> VisualizationSettings:
        """Get visualization configuration"""

        return VisualizationSettings(
            figure_size_large=(self.FIGURE_SIZE_LARGE_WIDTH, self.FIGURE_SIZE_LARGE_HEIGHT),
            figure_size_medium=(self.FIGURE_SIZE_MEDIUM_WIDTH, self.FIGURE_SIZE_MEDIUM_HEIGHT),
            dpi=self.DPI
        )

    @property
    def colors(self) -> ColorSettings:
        """Get color configuration"""

        return ColorSettings(
            success=self.SUCCESS_COLOR,
            failure=self.FAILURE_COLOR,
            grid_linestyle=self.GRID_LINESTYLE,
            grid_alpha=self.GRID_ALPHA
        )

    @property
    def thresholds(self) -> ScoreThresholds:
        """Get score threshold configuration"""

        return ScoreThresholds(
            highlight_good_score=self.HIGHLIGHT_GOOD_SCORE,
            highlight_bad_score=self.HIGHLIGHT_BAD_SCORE,
            fingerprint_good_trust_score=self.FINGERPRINT_GOOD_TRUST_SCORE,
            fingerprint_good_bot_score=self.FINGERPRINT_GOOD_BOT_SCORE
        )

    @property
    def filenames(self) -> FilenameSettings:
        """Get filename configuration"""

        return FilenameSettings(
            bypass_dashboard=self.BYPASS_DASHBOARD_FILENAME,
            bypass_rate=self.BYPASS_RATE_FILENAME,
            bypass_protection_heatmap=self.BYPASS_PROTECTION_HEATMAP_FILENAME,
            bypass_resource_usage=self.BYPASS_RESOURCE_USAGE_FILENAME,
            bypass_load_time=self.BYPASS_LOAD_TIME_FILENAME,
            timings_dashboard=self.TIMINGS_DASHBOARD_FILENAME,
            timing_startup=self.TIMING_STARTUP_FILENAME,
            timing_bypass=self.TIMING_BYPASS_FILENAME,
            timing_browser_data=self.TIMING_BROWSER_DATA_FILENAME,
            timing_overhead=self.TIMING_OVERHEAD_FILENAME,
            recaptcha_scores=self.RECAPTCHA_SCORES_FILENAME,
            fingerprint_scores=self.FINGERPRINT_SCORES_FILENAME,
            fingerprint_demo=self.FINGERPRINT_DEMO_FILENAME,
            incolumitas=self.INCOLUMITAS_FILENAME,
            deviceandbrowserinfo=self.DEVICEANDBROWSERINFO_FILENAME,
            scan_fingerprint=self.scan_fingerprint_FILENAME,
            summary=self.SUMMARY_FILENAME
        )

    model_config = {
        "case_sensitive": True,
        "extra": "ignore",
    }


report_settings = ReportSettings()
