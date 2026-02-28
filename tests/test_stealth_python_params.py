#!/usr/bin/env python3
import argparse
import asyncio
import contextlib
import functools
import http.server
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.engines import engines_config
from utils.js_script import load_js_script

pytestmark = pytest.mark.engine

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

SERVICE_WORKER_SCRIPT_NAME = "sw_probe.js"


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


def _service_worker_probe_script() -> str:
    return f"""
return (async () => {{
  if (!('serviceWorker' in navigator)) {{
    return JSON.stringify({{
      supported: false,
      reason: 'serviceWorker API unavailable'
    }});
  }}

  try {{
    const existing = await navigator.serviceWorker.getRegistrations();
    await Promise.all(existing.map((reg) => reg.unregister().catch(() => false)));
  }} catch (_err) {{
  }}

  const scriptUrl = '/{SERVICE_WORKER_SCRIPT_NAME}?v=' + Date.now();
  const registration = await navigator.serviceWorker.register(scriptUrl, {{ scope: '/' }});
  await navigator.serviceWorker.ready;
  const activeWorker =
    registration.active ||
    registration.waiting ||
    (await navigator.serviceWorker.ready).active;

  if (!activeWorker) {{
    return JSON.stringify({{
      supported: false,
      reason: 'service worker has no active instance'
    }});
  }}

  const workerNavigator = await new Promise((resolve, reject) => {{
    const timeout = setTimeout(() => {{
      reject(new Error('Timed out waiting for service worker response'));
    }}, 10000);
    const channel = new MessageChannel();
    channel.port1.onmessage = (event) => {{
      clearTimeout(timeout);
      resolve(event.data || null);
    }};
    activeWorker.postMessage({{ type: 'navigatorProbe' }}, [channel.port2]);
  }});

  await registration.unregister().catch(() => false);
  return JSON.stringify({{
    supported: true,
    navigator: workerNavigator
  }});
}})();
"""


def _service_worker_runtime_script() -> str:
    return """
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
  const port = event.ports && event.ports[0];
  if (!port) {
    return;
  }

  const nav = self.navigator || {};
  port.postMessage({
    userAgent: nav.userAgent ?? null,
    platform: nav.platform ?? null,
    language: nav.language ?? null,
    languages: nav.languages ?? null,
    hardwareConcurrency: nav.hardwareConcurrency ?? null,
    deviceMemory: nav.deviceMemory ?? null,
    maxTouchPoints: nav.maxTouchPoints ?? null
  });
});
"""


def _dedicated_worker_probe_script() -> str:
    return """
return (async () => {
  if (typeof Worker === 'undefined') {
    return JSON.stringify({
      supported: false,
      reason: 'Worker API unavailable'
    });
  }

  const workerSource = `
self.onmessage = function () {
  const nav = self.navigator || {};
  self.postMessage({
    userAgent: nav.userAgent ?? null,
    platform: nav.platform ?? null,
    language: nav.language ?? null,
    languages: nav.languages ?? null,
    hardwareConcurrency: nav.hardwareConcurrency ?? null,
    deviceMemory: nav.deviceMemory ?? null,
    maxTouchPoints: nav.maxTouchPoints ?? null
  });
};
`;
  const blob = new Blob([workerSource], { type: 'text/javascript' });
  const workerUrl = URL.createObjectURL(blob);

  try {
    const workerNavigator = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Timed out waiting for dedicated worker response'));
      }, 10000);
      const worker = new Worker(workerUrl);
      worker.onmessage = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        resolve(event.data || null);
      };
      worker.onerror = (event) => {
        clearTimeout(timeout);
        worker.terminate();
        reject(new Error(event.message || 'Dedicated worker error'));
      };
      worker.postMessage({ type: 'navigatorProbe' });
    });

    return JSON.stringify({
      supported: true,
      navigator: workerNavigator
    });
  } catch (err) {
    return JSON.stringify({
      supported: false,
      reason: String((err && err.message) ? err.message : err)
    });
  } finally {
    URL.revokeObjectURL(workerUrl);
  }
})();
"""


def _prepare_local_test_site(temp_dir: Path) -> Path:
    site_dir = temp_dir / "local_stealth_site"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(
        "<html><body>stealth params smoke</body></html>",
        encoding="utf-8",
    )
    (site_dir / SERVICE_WORKER_SCRIPT_NAME).write_text(
        _service_worker_runtime_script(),
        encoding="utf-8",
    )
    return site_dir


@contextlib.contextmanager
def _local_http_server(root_dir: Path):
    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    handler = functools.partial(_QuietHandler, directory=str(root_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


async def _validate_engine(
    engine_config: dict[str, Any],
    temp_dir: Path,
    page_url: str,
    test_service_worker: bool,
    test_dedicated_worker: bool,
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
        await engine.navigate(page_url)
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

        sw_status = "not-run"
        sw_mismatches = []
        sw_unsupported_fields: list[str] = []
        sw_probe: dict[str, Any] | None = None
        if test_service_worker:
            sw_raw = await engine.execute_js(_service_worker_probe_script())
            if isinstance(sw_raw, str):
                try:
                    sw_probe = json.loads(sw_raw)
                except Exception:
                    sw_probe = None
            elif isinstance(sw_raw, dict):
                sw_probe = sw_raw
            else:
                sw_probe = None
        else:
            sw_status = "skip (disabled)"

        if test_service_worker and isinstance(sw_probe, dict) and sw_probe.get("supported"):
            sw_nav = sw_probe.get("navigator")
            if isinstance(sw_nav, dict):
                for field in FIELDS_TO_ASSERT:
                    actual = sw_nav.get(field)
                    if actual is None:
                        sw_unsupported_fields.append(field)
                        continue
                    expected = expected_nav.get(field)
                    if actual != expected:
                        sw_mismatches.append(f"{field}: expected={expected!r}, actual={actual!r}")
                sw_status = "ok"
            else:
                sw_status = "invalid-response"
        elif test_service_worker and isinstance(sw_probe, dict):
            reason = sw_probe.get("reason", "unsupported")
            sw_status = f"skip ({reason})"
        elif test_service_worker:
            sw_status = "invalid-response"

        if mismatches:
            message = "\n  - ".join(mismatches)
            return False, f"{engine_name}: navigator mismatch:\n  - {message}"

        if sw_mismatches:
            message = "\n  - ".join(sw_mismatches)
            return False, f"{engine_name}: service worker navigator mismatch:\n  - {message}"

        dw_status = "not-run"
        dw_mismatches = []
        dw_unsupported_fields: list[str] = []
        dw_probe: dict[str, Any] | None = None
        if test_dedicated_worker:
            dw_raw = await engine.execute_js(_dedicated_worker_probe_script())
            if isinstance(dw_raw, str):
                try:
                    dw_probe = json.loads(dw_raw)
                except Exception:
                    dw_probe = None
            elif isinstance(dw_raw, dict):
                dw_probe = dw_raw
            else:
                dw_probe = None
        else:
            dw_status = "skip (disabled)"

        if test_dedicated_worker and isinstance(dw_probe, dict) and dw_probe.get("supported"):
            dw_nav = dw_probe.get("navigator")
            if isinstance(dw_nav, dict):
                for field in FIELDS_TO_ASSERT:
                    actual = dw_nav.get(field)
                    if actual is None:
                        dw_unsupported_fields.append(field)
                        continue
                    expected = expected_nav.get(field)
                    if actual != expected:
                        dw_mismatches.append(f"{field}: expected={expected!r}, actual={actual!r}")
                dw_status = "ok"
            else:
                dw_status = "invalid-response"
        elif test_dedicated_worker and isinstance(dw_probe, dict):
            reason = dw_probe.get("reason", "unsupported")
            dw_status = f"skip ({reason})"
        elif test_dedicated_worker:
            dw_status = "invalid-response"

        if dw_mismatches:
            message = "\n  - ".join(dw_mismatches)
            return False, f"{engine_name}: dedicated worker navigator mismatch:\n  - {message}"

        unsupported_note = ""
        if sw_unsupported_fields:
            unsupported_note += f", sw_unsupported={','.join(sw_unsupported_fields)}"
        if dw_unsupported_fields:
            unsupported_note += f", dw_unsupported={','.join(dw_unsupported_fields)}"
        summary = (
            f"{engine_name}: "
            f"hardwareConcurrency={actual_nav.get('hardwareConcurrency')}, "
            f"deviceMemory={actual_nav.get('deviceMemory')}, "
            f"maxTouchPoints={actual_nav.get('maxTouchPoints')}, "
            f"serviceWorker={sw_status}, "
            f"dedicatedWorker={dw_status}{unsupported_note}"
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


def _pick_engine_name() -> str:
    preferred_prefixes = [
        "patchright",
        "playwright-chrome",
        "playwright-firefox",
    ]
    names = [cfg.get("params", {}).get("name") for cfg in engines_config.engines]
    names = [name for name in names if isinstance(name, str) and name]
    for prefix in preferred_prefixes:
        for name in names:
            if name.startswith(prefix):
                return name
    if not names:
        raise AssertionError("No configured engines were found")
    return names[0]


async def _run(
    engine_names: list[str] | None,
    test_service_worker: bool = False,
    test_dedicated_worker: bool = True,
) -> int:
    engine_configs = _filter_engine_configs(engine_names)
    print(f"Engines to validate: {len(engine_configs)}")
    print(f"Service worker validation: {'enabled' if test_service_worker else 'disabled'}")
    print(f"Dedicated worker validation: {'enabled' if test_dedicated_worker else 'disabled'}")

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="stealth-runtime-check-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        site_dir = _prepare_local_test_site(temp_dir)
        with _local_http_server(site_dir) as page_url:
            for engine_config in engine_configs:
                engine_name = engine_config.get("params", {}).get("name", "unknown")
                #print(f"[RUN] {engine_name}")
                ok, details = await _validate_engine(
                    engine_config,
                    temp_dir=temp_dir,
                    page_url=page_url,
                    test_service_worker=test_service_worker,
                    test_dedicated_worker=test_dedicated_worker,
                )
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
    parser.add_argument(
        "--test-service-worker",
        action="store_true",
        help="Enable service worker navigator checks (disabled by default).",
    )
    parser.add_argument(
        "--test-dedicated-worker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable dedicated worker navigator checks (enabled by default). Use --no-test-dedicated-worker to disable.",
    )
    return parser.parse_args()


@pytest.mark.skipif(os.environ.get("RUN_ENGINE_TESTS") != "1", reason="Set RUN_ENGINE_TESTS=1 to run engine diagnostics")
def test_stealth_python_params() -> None:
    engine_name = _pick_engine_name()
    exit_code = asyncio.run(_run(engine_names=[engine_name]))
    assert exit_code == 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(
        _run(
            engine_names=args.engines,
            test_service_worker=args.test_service_worker,
            test_dedicated_worker=args.test_dedicated_worker,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
