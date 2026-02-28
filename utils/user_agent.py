import logging
from functools import lru_cache
from typing import Optional

from browserforge.headers import HeaderGenerator

logger = logging.getLogger(__name__)

_FALLBACK_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.6312.86 Safari/537.36"
)
_FALLBACK_FIREFOX_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)


@lru_cache(maxsize=1)
def _header_generator() -> HeaderGenerator:
    return HeaderGenerator()


def resolve_browser_family(browser_type: Optional[str], engine_name: Optional[str] = None) -> str:
    browser = (browser_type or "").strip().lower()
    name = (engine_name or "").strip().lower()

    if browser in {"firefox", "ff"}:
        return "firefox"
    if browser in {"chrome", "chromium", "edge", "webkit"}:
        return "chrome"

    if "firefox" in name or "camoufox" in name:
        return "firefox"

    return "chrome"


def generate_user_agent(browser_type: Optional[str], engine_name: Optional[str] = None) -> str:
    browser_family = resolve_browser_family(browser_type, engine_name)

    try:
        headers = _header_generator().generate(browser=browser_family, device="desktop")
        user_agent = headers.get("User-Agent")
        if user_agent:
            return user_agent
    except Exception as exc:
        logger.warning("Failed to generate %s user-agent via browserforge: %s", browser_family, exc)

    return _FALLBACK_FIREFOX_UA if browser_family == "firefox" else _FALLBACK_CHROME_UA
