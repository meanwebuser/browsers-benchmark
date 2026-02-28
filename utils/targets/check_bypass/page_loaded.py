import logging

from engines.base import BrowserEngine

logger = logging.getLogger(__name__)


async def check_page_loaded_bypass(engine: BrowserEngine) -> bool:
    """
    Basic check that the target page is rendered and no obvious anti-bot page is shown.

    :param engine: BrowserEngine instance
    """

    body_found, _ = await engine.locator("body")
    if not body_found:
        return False

    page_content = (await engine.get_page_content()).lower()
    blocked_markers = (
        "just a moment",
        "access denied",
        "forbidden",
        "are you human",
        "робот",
        "каптча",
        # Wildberries anti-bot page
        "что-то не так...",
        "подозрительная активность. пожалуйста, подождите.",
        "captcha-support@rwb.ru",
        "новая попытка через",
        # Ozon anti-bot page
        "доступ ограничен",
        "инцидент:",
        "fab_chlg_",
        # Avito anti-bot page
        "firewall-container",
        "доступ ограничен: проблема с ip",
        "geetest_captcha",
        "h-captcha",
    )

    for marker in blocked_markers:
        if marker in page_content:
            logger.info(
                "Page loaded bypass failed on engine %s: detected blocked marker '%s'",
                engine.name,
                marker
            )
            return False

    return True
