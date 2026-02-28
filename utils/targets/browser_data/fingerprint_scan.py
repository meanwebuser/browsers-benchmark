import asyncio
import logging
import re

from config.settings import settings
from engines.base import BrowserEngine

logger = logging.getLogger(__name__)


def _parse_bot_risk_score(text: str) -> int | None:
    match = re.search(r"Bot\s*Risk\s*Score:\s*(\d{1,3})\s*/\s*100", text, flags=re.IGNORECASE)
    if not match:
        return None

    try:
        score = int(match.group(1))
    except ValueError:
        return None

    if 0 <= score <= 100:
        return score
    return None


async def extract_fingerprint_scan_data(engine: BrowserEngine) -> dict:
    """
    Extract Bot Risk Score from fingerprint-scan.com.
    """

    script = """
const node = document.getElementById('fingerprintScore');
if (!node) return '';
return (node.textContent || '').trim();
"""

    timeout_s = settings.browser.page_load_timeout_s
    deadline = asyncio.get_event_loop().time() + timeout_s
    score_text = ""

    while asyncio.get_event_loop().time() < deadline:
        value = await engine.execute_js(script)
        if isinstance(value, str) and value.strip():
            score_text = value.strip()
            break
        await asyncio.sleep(1)

    if not score_text:
        logger.warning("%s: failed to extract #fingerprintScore text", engine.name)
        return {"fingerprint_scan_bot_risk_score": None}

    return {"fingerprint_scan_bot_risk_score": _parse_bot_risk_score(score_text)}
