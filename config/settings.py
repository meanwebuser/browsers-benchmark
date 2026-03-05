import os

from pydantic import BaseModel, PrivateAttr
from pydantic_settings import BaseSettings


class ProxySettings(BaseModel):
    """Configuration settings for the proxy"""

    enabled: bool = True  # Global on/off switch for proxy assignment and proxy health checks.
    file_path: str = "documents/proxies.txt"  # Source file with one proxy per line.
    db_path: str = "documents/proxies.sqlite"  # SQLite cache/state store for proxy manager runtime data.
    test_url: str = "http://httpbin.org/ip"  # URL used to quickly verify whether a proxy is alive.
    test_timeout: int = 10  # Timeout in seconds for proxy connectivity and direct-IP checks.
    debug_verify_usage: bool = False  # Test-only runtime flag: verify browser IP differs from direct IP.
    lock_stale_s: int = 3600  # Stale lock threshold: reclaim proxy lock after this many seconds.
    max_retries: int = 3  # Max proxy errors before exclusion (error_count < max_retries); 0 = unlimited.
    fallback_max_retries: int = 3  # Max per-target proxy fallback attempts; 0 = unlimited.

    model_config = {"extra": "ignore"}


class PathSettings(BaseModel):
    """Configuration settings for file paths"""

    documents_path: str = "documents"  # Root directory for project documents and runtime helper files.
    binaries_dir: str = "binaries"  # Subdirectory containing downloaded/managed browser binaries.
    profiles_dir: str = "profiles"  # Subdirectory for persisted browser profiles, when used.
    results_path: str = "results"  # Root output directory for benchmark runs.
    media_dir: str = "media"  # Subdirectory under each result containing charts/screenshots.
    screenshots_dir: str = "screenshots"  # Per-engine screenshots directory name.

    @property
    def binaries_path(self) -> str:
        return os.path.join(self.documents_path, self.binaries_dir)

    @property
    def profiles_path(self) -> str:
        return os.path.join(self.documents_path, self.profiles_dir)

    model_config = {"extra": "ignore"}


class BrowserSettings(BaseModel):
    """Configuration settings for browser engines"""

    action_timeout_s: int = 60  # Timeout for browser actions: locating elements, JS execution, screenshots, etc.
    page_load_timeout_s: int = 60  # Timeout for full page navigation and initial load completion.
    page_stabilization_delay_s: int = 5  # Delay after navigation to allow async page scripts/DOM to settle.
    mode: str = "both"  # Engine expansion mode: one of "headless", "headed", or "both".
    try_headed_without_display: bool = False  # Allow headed launches in environments that may lack DISPLAY.

    model_config = {"extra": "ignore"}


class Settings(BaseSettings):
    """Main application settings"""

    _proxy_debug_verify_usage_test_override: bool = PrivateAttr(default=False)

    # proxy
    PROXY_ENABLED: bool = True  # Enables proxy manager flow (assignment, health checks, fallback logic).
    PROXY_FILE_PATH: str = "documents/proxies.txt"  # File with proxies loaded at startup.
    PROXY_DB_PATH: str = "documents/proxies.sqlite"  # Persistent SQLite state for proxy locking/statistics.
    PROXY_TEST_URL: str = "http://httpbin.org/ip"  # Probe URL for checking whether a proxy can reach network.
    PROXY_TEST_TIMEOUT: int = 10  # Probe timeout (seconds) for proxy/direct IP checks.
    PROXY_LOCK_STALE_S: int = 3600  # Proxy lock recovery timeout (seconds).
    PROXY_MAX_RETRIES: int = 3  # Errors allowed before proxy becomes unusable; 0 disables this limit.
    PROXY_FALLBACK_MAX_RETRIES: int = 3  # Proxy fallback attempts per target; 0 = unlimited retries.

    # browser
    ACTION_TIMEOUT_S: int = 30  # Timeout for interactive actions (clicks/selectors/JS/screenshot).
    PAGE_LOAD_TIMEOUT_S: int = 90  # Hard timeout for page load/navigation.
    PAGE_STABILIZATION_DELAY_S: int = 5  # Post-navigation delay to reduce flaky signal extraction.
    ENGINES_TO_TEST_MODE: str = "both"  # Expand engines as headed/headless variants ("headless"|"headed"|"both").
    BROWSER_TRY_HEADED_WITHOUT_DISPLAY: bool = False  # Attempt headed mode in CI/server setups without display.
    ENGINE_STEALTH_MODE: str = "both"  # Expand stealth variants ("no_stealth"|"use_stealth"|"both").
    ENGINE_USER_AGENT_MODE: str = "random"  # User-agent strategy: generated random UA or engine-native.
    CAMOUFOX_UNLOCK_SHADOW_DOM: bool = True  # Enable Camoufox helper to expose Shadow DOM for selectors.
    NUM_WORKERS_MIN: int = 1  # Lower bound for parallel engine workers.
    NUM_WORKERS_MAX: int = 10  # Upper bound for parallel engine workers.
    BENCHMARK_REPEAT_COUNT: int = 1  # Number of repeated full runs per engine.
    ENGINE_MAX_ATTEMPTS: int = 30  # Max total target attempts per engine run; 0 = unlimited.
    ENGINE_PROXY_FALLBACK_MAX_ATTEMPTS: int | None = None  # Legacy alias for ENGINE_MAX_ATTEMPTS.
    ENGINE_RUN_TIMEOUT_S: int = 0  # Max wall-clock runtime per engine run; 0 = unlimited.

    # paths
    DOCUMENTS_PATH: str = "documents"  # Root documents directory.
    BINARIES_DIR: str = "binaries"  # Browser binaries directory name under DOCUMENTS_PATH.
    PROFILES_DIR: str = "profiles"  # Browser profiles directory name under DOCUMENTS_PATH.
    RESULTS_PATH: str = "results"  # Root benchmark output folder.
    MEDIA_DIR: str = "media"  # Media artifacts folder name inside each result.
    SCREENSHOTS_DIR: str = "screenshots"  # Screenshot artifacts folder name inside media.

    # constants
    MAX_RETRIES: int = 3  # Generic retry budget for recoverable benchmark operations.

    def set_proxy_debug_verify_usage_for_tests(self, enabled: bool) -> None:
        """
        Test-only runtime override for proxy usage verification.

        Not sourced from environment variables by design.
        """
        self._proxy_debug_verify_usage_test_override = bool(enabled)

    @property
    def proxy(self) -> ProxySettings:
        """Get proxy configuration"""
        fallback_max_retries = self.PROXY_FALLBACK_MAX_RETRIES
        return ProxySettings(
            enabled=self.PROXY_ENABLED,
            file_path=self.PROXY_FILE_PATH,
            db_path=self.PROXY_DB_PATH,
            test_url=self.PROXY_TEST_URL,
            test_timeout=self.PROXY_TEST_TIMEOUT,
            debug_verify_usage=self._proxy_debug_verify_usage_test_override,
            lock_stale_s=self.PROXY_LOCK_STALE_S,
            max_retries=self.PROXY_MAX_RETRIES,
            fallback_max_retries=fallback_max_retries,
        )

    @property
    def paths(self) -> PathSettings:
        """Get path configuration"""
        return PathSettings(
            documents_path=self.DOCUMENTS_PATH,
            binaries_dir=self.BINARIES_DIR,
            profiles_dir=self.PROFILES_DIR,
            results_path=self.RESULTS_PATH,
            media_dir=self.MEDIA_DIR,
            screenshots_dir=self.SCREENSHOTS_DIR
        )

    @property
    def browser(self) -> BrowserSettings:
        """Get browser configuration"""
        return BrowserSettings(
            action_timeout_s=self.ACTION_TIMEOUT_S,
            page_load_timeout_s=self.PAGE_LOAD_TIMEOUT_S,
            page_stabilization_delay_s=self.PAGE_STABILIZATION_DELAY_S,
            mode=self.ENGINES_TO_TEST_MODE,
            try_headed_without_display=self.BROWSER_TRY_HEADED_WITHOUT_DISPLAY
        )

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()
