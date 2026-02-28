import asyncio
import json
import logging
import os
from typing import Optional

from config.settings import settings
from engines.base import BrowserEngine

logger = logging.getLogger(__name__)


def _resolve_fingerprint_output_dir(engine: BrowserEngine) -> str:
    run_result_path = getattr(engine, "run_result_path", "") or ""
    base_path = run_result_path if run_result_path else settings.paths.results_path
    return os.path.join(base_path, "fingerprint_demo")


async def _click_browser_smart_signals_tab(engine: BrowserEngine, tries: int = 20) -> bool:
    click_script = """
const labels = Array.from(document.querySelectorAll('span[class*=\"tabLabel\"], span'));
const tab = labels.find((el) => {
  const text = (el.textContent || '').trim().toUpperCase();
  return text.includes('BROWSER SMART SIGNALS');
});
if (!tab || !tab.isConnected) return false;
tab.scrollIntoView({ block: 'center' });
tab.click();
return true;
"""

    for _ in range(tries):
        clicked = await engine.execute_js(click_script)
        if clicked:
            await asyncio.sleep(1.5)
            return True
        await asyncio.sleep(1)

    return False


async def _open_signal_details(engine: BrowserEngine) -> bool:
    click_script = """
const button = document.querySelector('button[class*=\"goArrowIcon\"]');
if (!button || !button.isConnected) return false;
button.scrollIntoView({ block: 'center' });
button.click();
return true;
"""

    for _ in range(10):
        clicked = await engine.execute_js(click_script)
        if clicked:
            await asyncio.sleep(2)
            return True
        await asyncio.sleep(1)

    return False


async def _extract_code_block(engine: BrowserEngine) -> str:
    code_script = """
const selector = '#gatsby-focus-wrapper > div:nth-child(6) > div > section > div.DiveIntoOurSignals-module--columns--87008 > div.DiveIntoOurSignals-module--codeColumn--6d1cf > div.DiveIntoOurSignals-module--codePanels--94462 > article:nth-child(2) > div > div > pre > code';
const exact = document.querySelector(selector);
if (exact && (exact.innerText || exact.textContent)) {
  return (exact.innerText || exact.textContent).trim();
}

const fallbackBlocks = Array.from(document.querySelectorAll('div[class*=\"codePanels\"] article:nth-child(2) pre code'));
const data = fallbackBlocks
  .map((el) => (el.innerText || el.textContent || '').trim())
  .filter(Boolean)
  .join('\\n\\n---\\n\\n');
return data;
"""

    timeout_s = settings.browser.page_load_timeout_s
    deadline = asyncio.get_event_loop().time() + timeout_s

    while asyncio.get_event_loop().time() < deadline:
        code = await engine.execute_js(code_script)
        if code:
            # Some engines return {"loading": true} as dict, others as a string.
            if isinstance(code, dict):
                if not code.get("loading"):
                    return str(code)
            else:
                text = str(code).strip()
                if '"loading": true' not in text:
                    return text
        await asyncio.sleep(1)

    return ""


def _save_demo_code(engine: BrowserEngine, code_text: str) -> str:
    output_dir = _resolve_fingerprint_output_dir(engine)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{engine.name}_signals_code.json")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(code_text)

    return output_path


def _extract_suspect_score(code_text: str) -> Optional[float]:
    try:
        payload = json.loads(code_text)
    except Exception:
        return None

    # fingerprint.com/demo exposes this at products.suspectScore.data.result
    if isinstance(payload, dict):
        result = (
            payload.get("products", {})
            .get("suspectScore", {})
            .get("data", {})
            .get("result")
        )
        if isinstance(result, (int, float)):
            return float(result)

    return None


async def extract_fingerprint_demo_data(engine: BrowserEngine) -> dict:
    """
    Extract Browser Smart Signals score and raw code sample from fingerprint.com/demo.
    """

    clicked_tab = await _click_browser_smart_signals_tab(engine)
    if not clicked_tab:
        logger.warning("%s: failed to open 'BROWSER SMART SIGNALS' tab", engine.name)

    opened_details = await _open_signal_details(engine)
    if not opened_details:
        logger.warning("%s: failed to open signal details via goArrowIcon", engine.name)

    code_text = await _extract_code_block(engine)
    file_path = ""
    suspect_score = None
    if code_text:
        file_path = _save_demo_code(engine, code_text)
        suspect_score = _extract_suspect_score(code_text)
        if suspect_score is None:
            logger.warning("%s: failed to parse suspectScore.data.result from demo JSON", engine.name)
    else:
        logger.warning("%s: failed to extract Fingerprint demo code block", engine.name)

    return {
        "fingerprint_untrust_score": None,
        "suspect_score": suspect_score,
        "fingerprint_webrtc_ip": "",
        "fingerprint_demo_file": file_path,
    }
