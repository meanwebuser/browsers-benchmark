#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.engines import engines_config
from utils.js_script import load_js_script

UA_BY_PLATFORM = {
    "chrome": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "firefox": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) "
        "Gecko/20100101 Firefox/136.0"
    ),
    "webkit": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.3 Safari/605.1.15"
    ),
}

FIELDS_TO_ASSERT = [
    "userAgent",
    "platform",
    "language",
    "languages",
    "hardwareConcurrency",
    "deviceMemory",
    "maxTouchPoints",
]

DATA_URL = "data:text/html,<html><body>stealth params smoke</body></html>"


def _extract_embedded_config(rendered_script: str) -> dict[str, Any]:
    matches = re.findall(r"\}\)\((\{.*?\})\);", rendered_script, re.DOTALL)
    if not matches:
        raise ValueError("Failed to extract embedded stealth config from rendered script")
    return json.loads(matches[-1])


def _normalize_platform(raw_browser_type: str | None, engine_name: str) -> str:
    value = (raw_browser_type or "").lower()
    if value in {"firefox"}:
        return "firefox"
    if value in {"webkit", "safari"}:
        return "webkit"

    engine_name_lc = engine_name.lower()
    if "firefox" in engine_name_lc or "camoufox" in engine_name_lc:
        return "firefox"
    if "webkit" in engine_name_lc or "safari" in engine_name_lc:
        return "webkit"
    return "chrome"


def _navigator_probe_script() -> str:
    return """
return JSON.stringify({
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language,
  languages: navigator.languages,
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory,
  maxTouchPoints: navigator.maxTouchPoints
});
"""


async def _validate_engine(
    engine_config: dict[str, Any],
    temp_dir: Path,
) -> tuple[bool, str]:
    engine_cls = engine_config["class"]
    params = dict(engine_config.get("params", {}))
    engine_name = params.get("name", engine_cls.__name__)

    engine = engine_cls(**params)
    browser_type = getattr(engine, "browser_type", None) or params.get("browser_type")
    platform = _normalize_platform(str(browser_type) if browser_type else None, engine_name)

    user_agent = getattr(engine, "user_agent", None) or params.get("user_agent") or UA_BY_PLATFORM[platform]
    rendered_stealth = await load_js_script(
        "stealth_improved.js",
        user_agent=user_agent,
        browser_type=platform,
    )
    expected_nav = _extract_embedded_config(rendered_stealth).get("navigator", {})

    script_path = temp_dir / f"{engine_name}.stealth.runtime.js"
    script_path.write_text(rendered_stealth, encoding="utf-8")

    if hasattr(engine, "user_agent"):
        setattr(engine, "user_agent", user_agent)
    if hasattr(engine, "init_scripts"):
        setattr(engine, "init_scripts", [str(script_path)])

    try:
        await engine.start()
        await engine.navigate(DATA_URL)
        await asyncio.sleep(0.5)
        actual_raw = await engine.execute_js(_navigator_probe_script())
        if isinstance(actual_raw, str):
            try:
                actual_nav = json.loads(actual_raw)
            except Exception:
                actual_nav = None
        elif isinstance(actual_raw, dict):
            actual_nav = actual_raw
        else:
            actual_nav = None

        mismatches = []
        for field in FIELDS_TO_ASSERT:
            expected = expected_nav.get(field)
            actual = actual_nav.get(field) if isinstance(actual_nav, dict) else None
            if actual != expected:
                mismatches.append(f"{field}: expected={expected!r}, actual={actual!r}")

        if mismatches:
            message = "\n  - ".join(mismatches)
            return False, f"{engine_name}: navigator mismatch:\n  - {message}"

        summary = (
            f"{engine_name}: "
            f"hardwareConcurrency={actual_nav.get('hardwareConcurrency')}, "
            f"deviceMemory={actual_nav.get('deviceMemory')}, "
            f"maxTouchPoints={actual_nav.get('maxTouchPoints')}"
        )
        return True, summary
    except Exception as e:
        return False, f"{engine_name}: runtime error: {e}"
    finally:
        try:
            await engine.stop()
        except Exception:
            pass


def _filter_engine_configs(requested_names: list[str] | None) -> list[dict[str, Any]]:
    all_configs = list(engines_config.engines)
    if not requested_names:
        return all_configs

    requested_set = set(requested_names)
    filtered = [cfg for cfg in all_configs if cfg.get("params", {}).get("name") in requested_set]
    found = {cfg.get("params", {}).get("name") for cfg in filtered}
    missing = sorted(requested_set - found)
    if missing:
        raise ValueError(f"Unknown engine names: {', '.join(missing)}")
    return filtered


async def _run(engine_names: list[str] | None) -> int:
    engine_configs = _filter_engine_configs(engine_names)
    print(f"Engines to validate: {len(engine_configs)}")

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="stealth-runtime-check-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        for engine_config in engine_configs:
            engine_name = engine_config.get("params", {}).get("name", "unknown")
            #print(f"[RUN] {engine_name}")
            ok, details = await _validate_engine(engine_config, temp_dir=temp_dir)
            if ok:
                print(f"[OK] {details}")
            else:
                print(f"[FAIL] {details}")
                failures.append(details)

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nAll engines passed.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run stealth Python-params validation across configured engines. "
            "Each engine is started and checked against navigator values from a Python-rendered stealth script."
        )
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        help="Optional list of engine names from config/engines.py; defaults to all configured engines.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(engine_names=args.engines))


if __name__ == "__main__":
    raise SystemExit(main())
