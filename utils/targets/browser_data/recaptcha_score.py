import asyncio
import logging
import re

from engines.base import BrowserEngine

logger = logging.getLogger(__name__)


def _extract_score_from_text(text: str) -> float | None:
    """
    Parse reCAPTCHA v3 score from arbitrary page text.
    """

    patterns = [r"Your score is:\s*([01](?:\.\d+)?)"]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
            except ValueError:
                continue
            if 0 <= score <= 1:
                return score
    return None


async def get_recaptcha_score_data(engine: BrowserEngine, tries: int = 10) -> dict:
    """
    Extract data from Recaptcha Score Detector page

    :param engine: BrowserEngine instance
    :param tries: Number of attempts to extract data
    """

    try:
        for i in range(tries):
            await asyncio.sleep(3)

            parts: list[str] = []

            try:
                js_text = await engine.execute_js(
                    """
const big = document.querySelector('div.row big');
if (big && (big.innerText || big.textContent)) {
  return (big.innerText || big.textContent).trim();
}
return (document.body && (document.body.innerText || document.body.textContent)) || '';
"""
                )
                if isinstance(js_text, str) and js_text.strip():
                    parts.append(js_text)
            except Exception:
                pass

            try:
                page_html = await engine.get_page_content()
                if page_html:
                    parts.append(page_html)
            except Exception:
                pass

            try:
                element_found, element_html = await engine.locator('div.row')
                if element_found and element_html:
                    parts.append(element_html)
            except Exception:
                pass

            combined_text = "\n".join(parts)
            if not combined_text:
                continue

            if re.search(r"(access denied|temporarily blocked|rate limit|forbidden)", combined_text, re.IGNORECASE):
                raise Exception("recaptcha page appears blocked or rate-limited")

            score = _extract_score_from_text(combined_text)
            if score is None:
                continue

            data = {"score": score}

            break
        else:
            raise Exception("Failed to extract recaptcha score data (recaptcha score not found, out of tries)")

        return data
    except Exception as e:
        raise Exception(f"Failed to extract recaptcha score data: {e}")


async def extract_recaptcha_score(engine: BrowserEngine) -> dict:
    """
    Extract Recaptcha Score from the page

    :param engine: BrowserEngine instance
    """

    for i in range(3):
        try:
            recaptcha_data = await get_recaptcha_score_data(engine)
            if recaptcha_data.get("score") is not None:
                break
        except Exception as e:
            logger.warning(f"Attempt {i + 1} failed: {e}")

        try:
            await engine.reload_page()
            logger.info('Page reloaded')
        except Exception as reload_error:
            logger.warning(f"Page reload failed: {reload_error}")
    else:
        raise Exception("Failed to extract recaptcha score data after multiple attempts")

    return {
        'recaptcha_score': recaptcha_data.get("score", 0)
    }
