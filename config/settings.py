import os

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ProxySettings(BaseModel):
    """Configuration settings for the proxy"""

    enabled: bool = True
    file_path: str = "documents/proxies.txt"
    db_path: str = "documents/proxies.sqlite"
    test_url: str = "http://httpbin.org/ip"
    test_timeout: int = 10
    debug_verify_usage: bool = False
    lock_stale_s: int = 3600
    max_retries: int = 3  # maximum number of proxy fallback attempts (0 = unlimited)

    model_config = {"extra": "ignore"}


class PathSettings(BaseModel):
    """Configuration settings for file paths"""

    documents_path: str = "documents"
    binaries_dir: str = "binaries"
    profiles_dir: str = "profiles"
    results_path: str = "results"
    media_dir: str = "media"
    screenshots_dir: str = "screenshots"

    @property
    def binaries_path(self) -> str:
        return os.path.join(self.documents_path, self.binaries_dir)

    @property
    def profiles_path(self) -> str:
        return os.path.join(self.documents_path, self.profiles_dir)

    model_config = {"extra": "ignore"}


class BrowserSettings(BaseModel):
    """Configuration settings for browser engines"""

    action_timeout_s: int = 60  # maximum time to wait for actions like search of elements, screenshots, clicks, etc.
    page_load_timeout_s: int = 60  # maximum time to wait for page load in seconds
    page_stabilization_delay_s: int = 5  # time to wait for page stabilization after navigation
    mode: str = "both"  # one of 'headless', 'headed', 'both'
    try_headed_without_display: bool = False

    model_config = {"extra": "ignore"}


class Settings(BaseSettings):
    """Main application settings"""

    # proxy
    PROXY_ENABLED: bool = True
    PROXY_FILE_PATH: str = "documents/proxies.txt"
    PROXY_DB_PATH: str = "documents/proxies.sqlite"
    PROXY_TEST_URL: str = "http://httpbin.org/ip"
    PROXY_TEST_TIMEOUT: int = 10
    PROXY_DEBUG_VERIFY_USAGE: bool = False
    PROXY_LOCK_STALE_S: int = 3600
    PROXY_MAX_RETRIES: int = 3  # 0 = unlimited proxy fallback retries

    # browser
    ACTION_TIMEOUT_S: int = 30  # maximum time to wait for actions like search of elements, screenshots, clicks, etc.
    PAGE_LOAD_TIMEOUT_S: int = 90  # maximum time to wait for page load in seconds
    PAGE_STABILIZATION_DELAY_S: int = 5  # time to wait for page stabilization after navigation
    ENGINES_TO_TEST_MODE: str = "both"  # one of 'headless', 'headed', 'both'
    BROWSER_TRY_HEADED_WITHOUT_DISPLAY: bool = False
    ENGINE_STEALTH_MODE: str = "both"  # one of 'no_stealth', 'use_stealth', 'both'
    ENGINE_USER_AGENT_MODE: str = "random"  # one of 'random', 'native'
    NUM_WORKERS_MIN: int = 1
    NUM_WORKERS_MAX: int = 10
    BENCHMARK_REPEAT_COUNT: int = 1

    # paths
    DOCUMENTS_PATH: str = "documents"
    BINARIES_DIR: str = "binaries"
    PROFILES_DIR: str = "profiles"
    RESULTS_PATH: str = "results"
    MEDIA_DIR: str = "media"
    SCREENSHOTS_DIR: str = "screenshots"

    # constants
    MAX_RETRIES: int = 3  # maximum retries for failed tests

    @property
    def proxy(self) -> ProxySettings:
        """Get proxy configuration"""
        return ProxySettings(
            enabled=self.PROXY_ENABLED,
            file_path=self.PROXY_FILE_PATH,
            db_path=self.PROXY_DB_PATH,
            test_url=self.PROXY_TEST_URL,
            test_timeout=self.PROXY_TEST_TIMEOUT,
            debug_verify_usage=self.PROXY_DEBUG_VERIFY_USAGE,
            lock_stale_s=self.PROXY_LOCK_STALE_S,
            max_retries=self.PROXY_MAX_RETRIES
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
