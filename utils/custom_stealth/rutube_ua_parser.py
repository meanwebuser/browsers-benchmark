import re
from typing import Dict, Any, List, Tuple, Callable, Optional, Union
from dataclasses import dataclass

# ===========================================================
# CONSTANTS
# ===========================================================
NAME = "name"
VERSION = "version"
MAJOR = "major"

MODEL = "model"
TYPE = "type"
VENDOR = "vendor"
ARCH = "architecture"
BITNESS = "bitness"

BROWSER = "browser"
CPU = "cpu"
DEVICE = "device"
ENGINE = "engine"
OS = "os"

CONSOLE = "console"
MOBILE = "mobile"
TABLET = "tablet"
SMARTTV = "smarttv"
WEARABLE = "wearable"
EMBEDDED = "embedded"

# ===========================================================
# UTILS
# ===========================================================
def _lower(s: Any) -> Any:
    return s.lower() if isinstance(s, str) else s

def _clean_version(v: str) -> str:
    return re.sub(r"[^\d.]", "", v)

def _major_version(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    cleaned = _clean_version(v)
    return cleaned.split(".")[0] if cleaned else None

def _replace(text: Optional[str], pattern: str, repl: str) -> Optional[str]:
    if not text:
        return None
    return re.sub(pattern, repl, text, flags=re.I)

def _regex(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)

# ===========================================================
# RULE TYPES
# ===========================================================
Rule = Union[
    str,                                           # NAME = group
    Tuple[str, Any],                               # key = fixed or function
    Tuple[str, str, str],                          # replace
    Tuple[str, str, str, Callable[[str], Any]]     # replace + func
]

RegexBlock = Tuple[List[re.Pattern], List[Rule]]
RegexMap = Dict[str, List[RegexBlock]]

def _apply_rule(target: Dict[str, Any], capture: Optional[str], rule: Rule) -> None:
    if isinstance(rule, str):
        target[rule] = capture
        return

    key = rule[0]

    # key, value OR key, func
    if len(rule) == 2:
        value = rule[1]
        if callable(value):
            target[key] = value(capture) if capture else None
        else:
            target[key] = value
        return

    # key, pattern, repl
    if len(rule) == 3:
        pat, repl = rule[1], rule[2]
        target[key] = _replace(capture, pat, repl)
        return

    # key, pattern, repl, func
    pat, repl, func = rule[1], rule[2], rule[3]
    replaced = _replace(capture, pat, repl)
    target[key] = func(replaced) if replaced else None

def _uses_capture(rule: Rule) -> bool:
    # simple NAME=group (string) → uses capture
    if isinstance(rule, str):
        return True

    # fixed rule: (key, value) where value not callable → no capture
    if isinstance(rule, tuple) and len(rule) == 2 and not callable(rule[1]):
        return False

    # all replace and function rules expect capture
    return True

def _apply_rules(target: Dict[str, Any], match: re.Match, rules: List[Rule]) -> None:
    group_i = 1
    max_i = match.lastindex or 0

    for rule in rules:
        if _uses_capture(rule):
            # this rule expects a capture group
            if group_i <= max_i:
                cap = match.group(group_i)
            else:
                cap = None
            group_i += 1
        else:
            # fixed rule – does NOT consume a capture group
            cap = None

        _apply_rule(target, cap, rule)

def _run_blocks(ua: str, blocks: List[RegexBlock], result: Dict[str, Any]) -> bool:
    for patterns, rules in blocks:
        for pat in patterns:
            m = pat.search(ua)
            if m:
                _apply_rules(result, m, rules)
                return True
    return False

# ===========================================================
# REGEX MAP — IMPROVED (2025)
# ===========================================================
EK: RegexMap = {
    BROWSER: [
        ([_regex(r"\bedg(?:e|ios|a)?\/([\d\.]+)")], [VERSION, (NAME, "Edge")]),
        ([_regex(r"\bopr\/([\d\.]+)")],             [VERSION, (NAME, "Opera")]),
        ([_regex(r"\bchrome\/([\d\.]+)")],          [VERSION, (NAME, "Chrome")]),
        ([_regex(r"\bfirefox\/([\d\.]+)")],         [VERSION, (NAME, "Firefox")]),
        ([_regex(r"version\/([\d\.]+).*safari")],   [VERSION, (NAME, "Safari")]),
        ([_regex(r"\bsamsungbrowser\/([\d\.]+)")],  [VERSION, (NAME, "Samsung Internet")]),
        ([_regex(r"\byabrowser\/([\d\.]+)")],       [VERSION, (NAME, "Yandex")]),
    ],

    OS: [
        ([_regex(r"windows nt ([\d\.]+)")],          [(NAME, "Windows"), VERSION]),
        ([_regex(r"mac os x\s*([0-9_\.]+)")],
         [
             (NAME, "Mac OS"),
             (VERSION, "_", ".", lambda v: v.replace("_", "."))
         ]),

        ([_regex(r"android(?: |/)([\d\.]+)")],       [(NAME, "Android"), VERSION]),
        ([_regex(r"cpu iphone os ([\d_]+)")],        [(NAME, "iOS"), (VERSION, "_", ".", lambda x: x.replace("_", "."))]),
        ([_regex(r"cpu os ([\d_]+) like mac os")],   [(NAME, "iOS"), (VERSION, "_", ".", lambda x: x.replace("_", "."))]),
        ([_regex(r"cros")],                          [(NAME, "Chrome OS")]),
        ([_regex(r"(ubuntu|debian|mint)")],          [(NAME, "Linux")]),
        ([_regex(r"linux")],                         [(NAME, "Linux")]),
    ],

    CPU: [
        ([_regex(r"(x86_64|amd64|wow64|x64)")], [(ARCH, "x86_64")]),
        ([_regex(r"(aarch64|arm64|armv8)")],    [(ARCH, "arm64")]),
        ([_regex(r"(i[3456]86|x86|ia32)")],     [(ARCH, "x86")]),
    ],

    DEVICE: [
        ([_regex(r"\((ipad).*?mac os")],            [(MODEL, "iPad"), (VENDOR, "Apple"), (TYPE, TABLET)]),
        ([_regex(r"\((iphone).*?mac os")],          [(MODEL, "iPhone"), (VENDOR, "Apple"), (TYPE, MOBILE)]),
        ([_regex(r"\((ipod)")],                    [(MODEL, "iPod"), (VENDOR, "Apple"), (TYPE, MOBILE)]),

        ([_regex(r"\b(sm-[a-z0-9]+)\b")],           [(MODEL, lambda m: m.upper()), (VENDOR, "Samsung"), (TYPE, MOBILE)]),
        ([_regex(r"\b(gt-[a-z0-9]+)\b")],           [(MODEL, lambda m: m.upper()), (VENDOR, "Samsung"), (TYPE, MOBILE)]),

        ([_regex(r"pixel ([0-9][0-9a-z ]*)")],            [(MODEL, lambda m: f"Pixel {m}"), (VENDOR, "Google"), (TYPE, MOBILE)]),

        ([_regex(r"android.*;\s([^);]+)\s+build")], [(MODEL, 1), (VENDOR, "Generic Android"), (TYPE, MOBILE)]),
    ],

    ENGINE: [
        ([_regex(r"applewebkit\/537\.36.*chrome")], [(NAME, "Blink"), (VERSION, "537.36")]),
        ([_regex(r"applewebkit\/([\d\.]+)")],       [(NAME, "WebKit"), VERSION]),
        ([_regex(r"gecko\/([\d\.]+)")],             [(NAME, "Gecko"), VERSION]),
        ([_regex(r"trident\/([\d\.]+)")],           [(NAME, "Trident"), VERSION]),
        ([_regex(r"edge\/([\d\.]+)")],              [(NAME, "EdgeHTML"), VERSION]),
    ]
}

# ===========================================================
# MAIN PARSER
# ===========================================================
def parse_ua(ua: str) -> Dict[str, Dict[str, Any]]:
    ua = ua.strip()
    result = {BROWSER: {}, OS: {}, CPU: {}, DEVICE: {}, ENGINE: {}}

    for section, blocks in EK.items():
        _run_blocks(ua, blocks, result[section])

    # add major versions
    for sec in (BROWSER, OS):
        if VERSION in result[sec]:
            result[sec][MAJOR] = _major_version(result[sec][VERSION])


    return result

import random

# =============================
# Пулы реалистичных GPU
# =============================

NVIDIA_GPUS_WIN = [
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1050 Ti/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1060 6GB/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1070/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1080/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 2060/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 2070/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 2080/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3050/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3070/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3080/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3090/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 4070/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 4080/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 4090/PCIe/SSE2"),
]

NVIDIA_GPUS_LINUX = [
    ("NVIDIA Corporation", "NVIDIA GeForce GTX 1660/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 2060 SUPER/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060 Ti/PCIe/SSE2"),
    ("NVIDIA Corporation", "NVIDIA GeForce RTX 3080 Ti/PCIe/SSE2"),
]

AMD_GPUS_WIN = [
    ("ATI Technologies Inc.", "AMD Radeon RX 5500 XT"),
    ("ATI Technologies Inc.", "AMD Radeon RX 5600 XT"),
    ("ATI Technologies Inc.", "AMD Radeon RX 5700 XT"),
    ("ATI Technologies Inc.", "AMD Radeon RX 580 Series"),
    ("ATI Technologies Inc.", "AMD Radeon RX Vega 56"),
    ("ATI Technologies Inc.", "AMD Radeon RX 6600 XT"),
    ("ATI Technologies Inc.", "AMD Radeon RX 6800 XT"),
    ("ATI Technologies Inc.", "AMD Radeon RX 7900 XTX"),
]

AMD_GPUS_LINUX = [
    ("X.Org", "Radeon RX 560 Series (POLARIS11, DRM 3.40.0, 5.15.0, LLVM 13.0.0)"),
    ("X.Org", "Radeon RX 5700 (NAVI10, DRM 3.40.0, LLVM 14.0.0)"),
]

INTEL_GPUS_WIN = [
    ("Intel Inc.", "Intel(R) HD Graphics 530"),
    ("Intel Inc.", "Intel(R) HD Graphics 630"),
    ("Intel Inc.", "Intel(R) UHD Graphics 620"),
    ("Intel Inc.", "Intel(R) UHD Graphics 630"),
    ("Intel Inc.", "Intel(R) Iris(R) Xe Graphics"),
]

INTEL_GPUS_MAC = [
    ("Intel Inc.", "Intel Iris Plus Graphics 655"),
    ("Intel Inc.", "Intel Iris Plus Graphics 640"),
    ("Intel Inc.", "Intel(R) UHD Graphics 617"),
]

INTEL_GPUS_LINUX = [
    ("Intel Inc.", "Mesa Intel(R) UHD Graphics 620"),
    ("Intel Inc.", "Mesa Intel(R) UHD Graphics 630"),
    ("Intel Inc.", "Mesa Intel(R) Graphics (TGL GT2)"),
]

APPLE_SILICON_GPUS = [
    ("Apple Inc.", "Apple M1"),
    ("Apple Inc.", "Apple M1 Pro"),
    ("Apple Inc.", "Apple M1 Max"),
    ("Apple Inc.", "Apple M2"),
    ("Apple Inc.", "Apple M2 Pro"),
    ("Apple Inc.", "Apple M3"),
]

CHROME_OS_GPUS = [
    ("Intel Inc.", "Mesa Intel(R) UHD Graphics 600"),
    ("ARM", "Mali-T864"),
    ("Qualcomm", "Adreno (TM) 630"),
]

ANDROID_ADRENO = [
    ("Qualcomm", "Adreno (TM) 630"),
    ("Qualcomm", "Adreno (TM) 640"),
    ("Qualcomm", "Adreno (TM) 650"),
    ("Qualcomm", "Adreno (TM) 660"),
    ("Qualcomm", "Adreno (TM) 730"),
    ("Qualcomm", "Adreno (TM) 740"),
]

ANDROID_MALI = [
    ("ARM", "Mali-G76"),
    ("ARM", "Mali-G77"),
    ("ARM", "Mali-G78"),
    ("ARM", "Mali-G710"),
]

VR_WEBCAM_DEVICES = [
    ("Qualcomm", "Adreno (TM) 650 - Oculus Browser"),
    ("Qualcomm", "Adreno (TM) 530 - Oculus Quest"),
]

WEAR_OS_GPUS = [
    ("ARM", "Mali-T720"),
    ("ARM", "Mali-G31"),
]

def get_realistic_webgl(os_name: str, arch: str, ua: str = "") -> Tuple[str, str]:
    """
    Возвращает (webgl_vendor, renderer) для заданной ОС / архитектуры / UA.
    Подбирает ТОЛЬКО реалистичные сочетания.
    """
    os_low = (os_name or "").lower()
    arch_low = (arch or "").lower()
    ua_low = (ua or "").lower()

    pool: List[Tuple[str, str]] = []

    # --- iOS / iPadOS / iPhone ---
    if "ios" in os_low or "iphone" in ua_low or "ipad" in ua_low:
        # В реальности WebGL там сильно абстрактный, но считаем Apple GPU
        pool = APPLE_SILICON_GPUS

    # --- macOS ---
    elif "mac" in os_low:
        if "intel" in ua_low or arch_low.startswith("x86"):
            # Старые Макбуки на Intel
            pool = INTEL_GPUS_MAC
        else:
            # M1/M2/M3
            pool = APPLE_SILICON_GPUS

    # --- Windows ---
    elif "win" in os_low:
        # Если в UA явно есть nvidia/amd/intel – усиливаем bias к соответствующему пулу
        if "nvidia" in ua_low:
            pool = NVIDIA_GPUS_WIN + INTEL_GPUS_WIN  # иногда в системе два GPU
        elif "amd" in ua_low or "radeon" in ua_low:
            pool = AMD_GPUS_WIN + INTEL_GPUS_WIN
        else:
            # любой реалистичный виндовый набор
            pool = NVIDIA_GPUS_WIN + AMD_GPUS_WIN + INTEL_GPUS_WIN

    # --- Android ---
    elif "android" in os_low:
        # Pixel / высокие девайсы — чаще Adreno
        if any(x in ua_low for x in ("pixel", "snapdragon", "sm-", "oneplus", "redmi", "xiaomi")):
            pool = ANDROID_ADRENO + ANDROID_MALI
        else:
            # универсальный Android
            pool = ANDROID_ADRENO + ANDROID_MALI + WEAR_OS_GPUS

    # --- Chrome OS ---
    elif "cros" in os_low or "chrome os" in os_low:
        pool = CHROME_OS_GPUS + INTEL_GPUS_LINUX

    # --- Linux десктоп ---
    elif "linux" in os_low:
        pool = NVIDIA_GPUS_LINUX + AMD_GPUS_LINUX + INTEL_GPUS_LINUX

    # --- Fallback (если не распознали) ---
    if not pool:
        pool = INTEL_GPUS_LINUX


    return random.choice(pool)

# ===========================================================
# MAKE STEALTH PARAMS (IMPROVED 2025)
# ===========================================================
def ua_to_stealth_params(ua: str) -> Dict[str, Any]:
    p = parse_ua(ua)
    ua_low=ua.lower()

    os_name = p[OS].get(NAME, "")
    arch = p[CPU].get(ARCH, "x86_64")
    device_type = p[DEVICE].get(TYPE)
    browser = p[BROWSER].get(NAME, "").lower()
    os_low = os_name.lower()

    # ==============================================
    # PLATFORM + platformVersion (главная правка)
    # ==============================================
    os_ver = p[OS].get(VERSION, "")  # типа "13.1" или "10.15.7"
    os_major = None

    if os_ver:
        # преобразуем “10.15.7” → “10”
        os_major = os_ver.split(".")[0]
    else:
        # fallback если версия не извлеклась
        os_major = None

    # ---------------- macOS ----------------
    if "mac" in os_low:
        platform = "MacIntel"

        platform_version = f"13.0.0" if arch.startswith("x86")  else f"14.0.0"


    # ---------------- Windows ----------------
    elif "win" in os_low:
        platform = "Win32"

        # Windows NT → Chrome всегда даёт platformVersion “15.0.0”
        # но правильнее построить из NT:
        nt_ver = p[OS].get(VERSION, "")
        # Windows NT 10.0 → 10
        if nt_ver and nt_ver[0].isdigit():
            major = nt_ver.split(".")[0]
            # Chrome нормирует NT → платформенную — Windows 10/11 = "15.0.0"
            # Но чтобы не быть палевным — можно использовать Chrome-like rule:
            platform_version = "15.0.0"
        else:
            platform_version = "15.0.0"

    # ---------------- Android ----------------
    elif "android" in os_low:
        platform  = "Android"

        # Android CH platformVersion = major Android version (строго)
        if os_major and os_major.isdigit():
            platform_version = f"{os_major}.0.0"
        else:
            platform_version = "13.0.0"

    # ---------------- iOS / iPadOS ----------------
    elif "ios" in os_low:
        platform = "iPhone" if device_type == MOBILE else "iPad"

        # iOS 17.3 → platformVersion = "17.0.0"
        if os_major and os_major.isdigit():
            platform_version = f"{os_major}.0.0"
        else:
            platform_version = "17.0.0"

    # ---------------- Linux desktop ----------------
    else:
        platform = "Linux x86_64"
        platform_version = "0.0.0"

    # ==============================================
    # WebGL
    # ==============================================
    webgl_vendor, renderer = get_realistic_webgl(os_name, arch, ua)

    # ==============================================
    # navigator.vendor
    # ==============================================
    if browser in ("chrome", "edge", "opera", "yabrowser", "samsungbrowser"):
        vendor = "Google Inc."
    elif browser == "safari":
        vendor = "Apple Computer, Inc."
    else:
        vendor = ""

    # ==============================================
    # architecture → CH format
    # ==============================================
    if "arm64" in arch:
        ch_arch = "arm64"
        ch_bitness = "64"
    elif "arm" in arch:
        ch_arch = "arm"
        ch_bitness = "32"
    elif "64" in arch:
        ch_arch = "x86"
        ch_bitness = "64"
    else:
        ch_arch = "x86"
        ch_bitness = "32"

    # iOS always arm64
    if "iphone" in ua_low or "ipad" in ua_low or "cpu iphone" in ua_low:
        ch_arch = "arm64"
        ch_bitness = "64"

    # Android almost always arm64 on modern devices
    elif "android" in ua_low:
        ch_arch = "arm64"
        ch_bitness = "64"

    # ==============================================
    # Browser version
    # ==============================================
    version = p[BROWSER].get(VERSION, "120")
    # Из UA берём чистую major.minor.patch если есть
    full_version = version

    # ==============================================
    # Client Hints brands
    # ==============================================
    brands = [
        {"brand": browser.capitalize() or "Google Chrome", "version": version},
        {"brand": "Chromium", "version": version},
        {"brand": "Not=A?Brand", "version": "24"}
    ]

    full_version_list = [
        {"brand": brands[0]["brand"], "version": full_version},
        {"brand": "Chromium", "version": full_version},
        {"brand": "Not=A?Brand", "version": "24.0.0.0"}
    ]

    # ==============================================
    # mobile flag
    # ==============================================
    mobile = device_type in (MOBILE, TABLET)

    # ==============================================
    # model
    # ==============================================
    model = p[DEVICE].get(MODEL) or ""

    # ==============================================
    # Final return
    # ==============================================
    return {
        "platform": platform,
        "userAgent": ua,
        "vendor": vendor,

        "renderer": renderer,
        "webgl_vendor": webgl_vendor,

        "uaClientHints": {
            "brands": brands,
            "fullVersionList": full_version_list,
            "mobile": mobile,
            "platform": platform,
            "platformVersion": platform_version,
            "architecture": ch_arch,
            "bitness": ch_bitness,
            "model": model,
            "uaFullVersion": full_version,
        },

        "mobile": mobile,
    }




# ===========================================================
# TEST
# ===========================================================
if __name__ == "__main__":
    tests = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    ]

    for ua in tests:
        print("\nUA:", ua)
        print("Parsed:", parse_ua(ua))
        print("Stealth:", ua_to_stealth_params(ua))

    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.70 Safari/537.36"
    print(ua)
    print(parse_ua(ua))
    from proxies import random_useragent
    import config_env
    config_env.config.SERVER_URL='http://bezrabotnyi.com:8888'
    ua=random_useragent()
    print(ua)
    print(parse_ua(ua))
