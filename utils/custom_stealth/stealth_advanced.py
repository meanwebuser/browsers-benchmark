import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

from utils.custom_stealth.rutube_ua_parser import ua_to_stealth_params


# ==========================
# БОЛЬШАЯ БАЗА РЕАЛИСТИЧНЫХ ЗНАЧЕНИЙ (2024–2025)
# ==========================

WEBGL_VENDORS = [
    # Intel
    "Intel Inc.", "Intel Open Source Technology Center",
    # NVIDIA
    "NVIDIA Corporation",
    # AMD
    "ATI Technologies Inc.", "AMD", "Advanced Micro Devices, Inc.",
    # Apple
    "Apple Inc.", "Apple GPU",
    # Qualcomm
    "Qualcomm", "Adreno",
    # ARM
    "ARM", "Mali",
    # Google (Angle)
    "Google Inc.", "Google SwiftShader", "Google Inc. (NVIDIA)", "Google Inc. (AMD)",
]

RENDERERS = [
    # Intel
    "Intel Iris Xe Graphics", "Intel UHD Graphics 630", "Intel HD Graphics 620",
    "Intel Iris Plus Graphics 655", "Intel UHD Graphics",
    # NVIDIA
    "NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 3080", "NVIDIA GeForce GTX 1660 Ti",
    "NVIDIA GeForce MX450", "NVIDIA T1200 Laptop GPU",
    # AMD
    "AMD Radeon RX 7900 XTX", "AMD Radeon RX 6800 XT", "AMD Radeon Pro WX 4100",
    "AMD Radeon Graphics", "AMD Radeon RX 6600M",
    # Apple
    "Apple M2", "Apple M1 Pro", "Apple M3 Max", "Apple A17 Pro",
    # Mobile
    "Adreno (TM) 740", "Adreno (TM) 650", "Mali-G78", "Mali-G710",
    # Fallback / Software
    "Google SwiftShader", "ANGLE (Software Renderer)",
]

VENDORS = [
    "Google Inc.", "Apple Inc.", "Microsoft Corporation", "Mozilla Foundation",
    "The Chromium Authors", "Samsung Electronics", "Lenovo", "ASUSTeK COMPUTER INC."
]

PLATFORMS_DESKTOP = ["Win32", "MacIntel", "Linux x86_64", "Linux armv8l"]
PLATFORMS_MOBILE = ["Linux aarch64", "Linux armv7l", "iPhone", "iPad"]

# Реальные пары vendor → renderer (для консистентности)
CONSISTENT_WEBGL_PAIRS = {
    "Intel Inc.": ["Intel Iris Xe Graphics", "Intel UHD Graphics 630", "Intel HD Graphics 620"],
    "Intel Open Source Technology Center": ["Mesa DRI Intel", "Intel Iris OpenGL Engine"],
    "NVIDIA Corporation": [r for r in RENDERERS if "NVIDIA" in r or "GeForce" in r],
    "AMD": [r for r in RENDERERS if "AMD" in r or "Radeon" in r],
    "Apple Inc.": [r for r in RENDERERS if "Apple" in r],
    "Qualcomm": [r for r in RENDERERS if "Adreno" in r],
    "ARM": [r for r in RENDERERS if "Mali" in r],
    "Google Inc.": ["Google SwiftShader", "ANGLE (NVIDIA", "ANGLE (AMD"],
}


def evaluationString(fun: str, *args: Any) -> str:
    """Сериализует функцию и экранирует аргументы для CDP."""
    _args = ", ".join([
        "undefined" if arg is None else json.dumps(arg, ensure_ascii=False)
        for arg in args
    ])
    return f"({fun})({_args});"


def evaluateOnNewDocument(driver, pagefunction: str, *args: Any) -> None:
    js_code = evaluationString(pagefunction, *args)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": js_code})


def get_consistent_webgl_pair(vendor: str) -> tuple[str, str]:
    """Возвращает совместимые vendor + renderer."""
    if vendor in CONSISTENT_WEBGL_PAIRS and random.random() < 0.85:  # 85% шанс консистентной пары
        renderer = random.choice(CONSISTENT_WEBGL_PAIRS[vendor])
    else:
        renderer = random.choice(RENDERERS)
    return vendor, renderer


def build_stealth_config(
    agent: str,
    *,
    is_mobile: bool | None = None,
    platform: str = "chrome",
) -> Dict[str, Any]:
    props = ua_to_stealth_params(agent)
    ch = props["uaClientHints"]
    mobile_flag = ch.get("mobile", False) if is_mobile is None else is_mobile

    languages = random.choice([
        ["ru-RU", "ru", "en-US", "en"],
        ["ru"],
        ["ru", "en-US", "en"],
    ])

    if mobile_flag:
        platform_val = random.choice(PLATFORMS_MOBILE)
    else:
        platform_val = props.get("platform") or random.choice(PLATFORMS_DESKTOP)

    client_hints = {
        "brands": ch["brands"],
        "fullVersionList": ch["fullVersionList"],
        "mobile": ch["mobile"],
        "platform": platform_val,
        "platformVersion": ch["platformVersion"],
        "architecture": ch["architecture"],
        "bitness": ch["bitness"],
        "model": ch["model"],
        "uaFullVersion": ch["uaFullVersion"],
    }

    stealth_config = {
        "platform": str(platform or "chrome").lower(),
        "navigator": {
            "userAgent": agent,
            "platform": platform_val,
            "vendor": props["vendor"],
            "languages": languages,
            "language": languages[0],
        },
        "uaClientHints": client_hints,
        "webgl": {
            "vendor": props["webgl_vendor"],
            "renderer": props["renderer"],
        },
    }

    tz = random.choice([
        "Europe/Moscow", "Asia/Yekaterinburg",
        "Asia/Novosibirsk", "Asia/Vladivostok",
    ])

    def get_offset_minutes(tz_name: str) -> int:
        now = datetime.now(ZoneInfo(tz_name))
        offset = now.utcoffset()
        return -int(offset.total_seconds() // 60)

    stealth_config["timezone"] = {
        "id": tz,
        "offsetMinutes": get_offset_minutes(tz),
    }

    if mobile_flag:
        cpu = random.randint(4, 8)
        mem = random.choice([2, 4, 8])
        max_touch = random.randint(5, 10)
    else:
        cpu = random.choice([4, 6, 8, 12, 16])
        mem = random.choice([4, 8])
        max_touch = 0

    stealth_config["navigator"] |= {
        "hardwareConcurrency": cpu,
        "deviceMemory": mem,
        "maxTouchPoints": max_touch,
    }

    return stealth_config


def render_stealth_script(
    agent: str,
    *,
    is_mobile: bool | None = None,
    stealth_script: str = "stealth_improved",
    platform: str = "chrome",
) -> str:
    configured_name = str(stealth_script or "stealth_improved").strip()
    configured_file = f"{configured_name}.js" if not configured_name.endswith(".js") else configured_name

    js_base_dir = Path(__file__).resolve().parent.parent / "js_scripts"
    candidates = [
        js_base_dir / configured_file,
        js_base_dir / "stealth_improved.js",
        js_base_dir / "all_in_one_steath.js",
        Path("stealth") / configured_file,
        Path("stealth") / "stealth_improved.js",
        Path("stealth") / "all_in_one_steath.js",
    ]

    tpl = None
    chosen_path = None
    for script_path in candidates:
        if script_path.exists():
            tpl = script_path.read_text(encoding="utf-8")
            chosen_path = script_path
            break

    if tpl is None:
        raise FileNotFoundError(f"No stealth script found. Checked: {[str(p) for p in candidates]}")

    logging.debug("Stealth script selected: %s", chosen_path)
    stealth_config = build_stealth_config(agent=agent, is_mobile=is_mobile, platform=platform)
    return tpl.replace("/*CONFIG_INJECTION*/", json.dumps(stealth_config, ensure_ascii=False))


def configure_stealth(
    driver,
    agent: str,
    *,
    is_mobile: bool | None = None,
    stealth_script: str = "stealth_improved",
    platform: str = "chrome",
):
    final_js = render_stealth_script(
        agent=agent,
        is_mobile=is_mobile,
        stealth_script=stealth_script,
        platform=platform,
    )
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": final_js})
