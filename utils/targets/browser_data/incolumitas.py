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
    return os.path.join(base_path, "incolumitas")


def _save_payload(engine: BrowserEngine, payload: dict[str, Any]) -> str:
    output_dir = _resolve_output_dir(engine)
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{engine.name}_browser_data_{timestamp}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path


async def extract_incolumitas_data(engine: BrowserEngine) -> dict:
    """
    Extract JSON payloads from bot.incolumitas.com browserData blocks.
    """

    script = """
const ids = ['webWorkerRes', 'fp', 'detection-tests', 'new-tests'];
const result = {};
for (const id of ids) {
  const el = document.getElementById(id);
  result[id] = el ? (el.textContent || '').trim() : '';
}
return result;
"""

    timeout_s = settings.browser.page_load_timeout_s
    deadline = asyncio.get_event_loop().time() + timeout_s
    raw_payload: dict[str, str] = {}

    while asyncio.get_event_loop().time() < deadline:
        data = await engine.execute_js(script)
        if isinstance(data, dict):
            raw_payload = {k: str(v or "").strip() for k, v in data.items()}
            if raw_payload.get("fp"):
                break
        await asyncio.sleep(1)

    parsed_payload: dict[str, Any] = {}
    for key, raw in raw_payload.items():
        if not raw:
            parsed_payload[key] = {}
            continue
        try:
            parsed_payload[key] = json.loads(raw)
        except Exception:
            parsed_payload[key] = {"raw": raw}

    if not parsed_payload:
        logger.warning("%s: failed to extract incolumitas payloads", engine.name)
        return {"incolumitas_file": ""}

    file_path = _save_payload(engine, parsed_payload)
    return {"incolumitas_file": file_path}
