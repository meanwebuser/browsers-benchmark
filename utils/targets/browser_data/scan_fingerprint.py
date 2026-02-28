import asyncio
import logging
import re

from config.settings import settings
from engines.base import BrowserEngine

logger = logging.getLogger(__name__)

#https://fingerprint-scan.com/
def _parse_bot_risk_score(text: str) -> int | None:
    match = re.search(r"Bot\s*Risk\s*Score:\s*(\d{1,3})\s*/\s*100", text, flags=re.IGNORECASE)
    if not match:
        return None

    try:
        score = int(match.group(1))
    except ValueError:
        return None

    return score if 0 <= score <= 100 else None


async def extract_scan_fingerprint_data(engine: BrowserEngine) -> dict:
    """
    Extract Bot Risk Score from fingerprint-scan.com.
    """
    script = """
const node = document.getElementById('fingerprintScore');
return node ? (node.textContent || '').trim() : '';
"""

    timeout_s = settings.browser.page_load_timeout_s
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s

    last_text = ""

    while loop.time() < deadline:
        value = await engine.execute_js(script)

        if isinstance(value, str):
            text = value.strip()
            if text:
                last_text = text
                score = _parse_bot_risk_score(text)
                if score is not None:
                    return {"scan_fingerprint_bot_risk_score": score}

        await asyncio.sleep(1)

    if not last_text:
        logger.warning("%s: failed to extract #fingerprintScore text", engine.name)
    else:
        logger.warning("%s: got #fingerprintScore text but couldn't parse score: %r", engine.name, last_text)

    return {"scan_fingerprint_bot_risk_score": None}