import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

from config.settings import settings
from engines.base import BrowserEngine

logger = logging.getLogger(__name__)


def _resolve_output_dir(engine: BrowserEngine) -> str:
    run_result_path = getattr(engine, "run_result_path", "") or ""
    base_path = run_result_path if run_result_path else settings.paths.results_path
    return os.path.join(base_path, "deviceandbrowserinfo")


def _save_payload(engine: BrowserEngine, payload: dict[str, Any]) -> str:
    output_dir = _resolve_output_dir(engine)
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{engine.name}_are_you_a_bot_{timestamp}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path


def _collect_bool_values(payload: Any) -> list[bool]:
    values: list[bool] = []
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, bool):
            values.append(current)
    return values


async def extract_deviceandbrowserinfo_data(engine: BrowserEngine) -> dict:
    """
    Extract bot detection JSON from deviceandbrowserinfo.com/are_you_a_bot.
    """

    script = """
const code = document.getElementById('jsonResult');
if (!code) return '';
return (code.textContent || '').trim();
"""

    timeout_s = settings.browser.page_load_timeout_s
    deadline = asyncio.get_event_loop().time() + timeout_s
    raw_text = ""

    while asyncio.get_event_loop().time() < deadline:
        value = await engine.execute_js(script)
        if isinstance(value, str) and value.strip():
            raw_text = value.strip()
            break
        await asyncio.sleep(1)

    if not raw_text:
        logger.warning("%s: failed to extract #jsonResult from deviceandbrowserinfo", engine.name)
        return {
            "deviceandbrowserinfo_is_bot": None,
            "deviceandbrowserinfo_file": "",
            "deviceandbrowserinfo_data": None,
        }

    try:
        payload = json.loads(raw_text)
    except Exception:
        payload = {"raw": raw_text}

    file_path = _save_payload(engine, payload)

    details_payload = payload.get("details") if isinstance(payload, dict) else None
    bool_values = _collect_bool_values(details_payload if details_payload is not None else payload)
    total_signals = len(bool_values)
    true_signals = sum(1 for value in bool_values if value)

    derived_is_bot = any(bool_values) if bool_values else None
    fallback_is_bot = payload.get("isBot") if isinstance(payload, dict) else None
    is_bot = derived_is_bot if derived_is_bot is not None else fallback_is_bot

    suspect_score = None
    if total_signals > 0:
        suspect_score = (true_signals / total_signals) * 100.0

    return {
        "deviceandbrowserinfo_is_bot": bool(is_bot) if is_bot is not None else None,
        "deviceandbrowserinfo_file": file_path,
        "deviceandbrowserinfo_suspect_score": suspect_score,
        "deviceandbrowserinfo_data": payload,
    }
