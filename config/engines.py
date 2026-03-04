import os
import re
from typing import List, Dict, Any, Set

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from config.settings import settings
from engines.hero.ulixee_hero_engine import UlixeeHeroEngine
from engines.node.node_playwright_engine import NodePlaywrightEngine
from engines.nodriver.nodriver_engine import NoDriverEngine
from engines.nodriver.seleniumbase_engine import SeleniumbaseEngine
from engines.nodriver.zendriver_engine import ZenDriverEngine
from engines.playwright.camoufox_engine import CamoufoxEngine
from engines.playwright.patchright_engine import PatchrightEngine
from engines.playwright.playwright_engine import PlaywrightEngine
from engines.playwright.tf_playwright_stealth_engine import TfPlaywrightStealthEngine
from engines.selenium.selenium_engine import SeleniumEngine
from engines.seleniumbase_uc import SeleniumBaseUCEngine
from utils.user_agent import generate_user_agent

STEALTH_INIT_SCRIPTS = ["stealth_improved.obf.js"]
ALLOWED_ENGINE_STEALTH_MODES = {"no_stealth", "use_stealth", "both"}
ALLOWED_ENGINE_USER_AGENT_MODES = {"random", "native"}
ALLOWED_ENGINES_TO_TEST_MODES = {"headless", "headed", "both"}

_ENGINE_MODE_SUFFIX_RE = re.compile(r"_(headless|headed|with_stealth)$")


def resolve_mode(value: str, allowed: Set[str], default: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else default


def _strip_engine_mode_suffixes(name: str) -> str:
    normalized = (name or "").strip()
    while normalized and _ENGINE_MODE_SUFFIX_RE.search(normalized):
        normalized = _ENGINE_MODE_SUFFIX_RE.sub("", normalized)
    return normalized


def _is_with_stealth(engine_cls: Any, params: Dict[str, Any]) -> bool:
    explicit = params.get("with_stealth")
    if explicit is not None:
        return bool(explicit)

    if engine_cls is TfPlaywrightStealthEngine:
        return True

    init_scripts = params.get("init_scripts", [])
    return any(script in STEALTH_INIT_SCRIPTS for script in init_scripts)


def _apply_engine_name_suffixes(engine_cls: Any, params: Dict[str, Any]) -> None:
    base_name = _strip_engine_mode_suffixes(str(params.get("name") or "engine"))
    suffixes: List[str] = []

    if "headless" in params:
        suffixes.append("headless" if bool(params.get("headless", True)) else "headed")

    with_stealth = _is_with_stealth(engine_cls, params)
    params["with_stealth"] = with_stealth
    if with_stealth:
        suffixes.append("with_stealth")

    params["name"] = f"{base_name}_{'_'.join(suffixes)}" if suffixes else base_name


class EngineConfig(BaseModel):
    """Configuration for a browser engine"""

    class_name: str = Field(..., description="Engine class name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Engine parameters")

    model_config = {"extra": "ignore"}


class EnginesSettings(BaseSettings):
    """Configuration for all browser engines"""

    engines: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of engine configurations"
    )

    def __init__(self, **data):
        """
        Initialize the EnginesSettings with the given data and initialize default engine configurations

        :param data: Keyword arguments for EnginesSettings
        """
        super().__init__(**data)
        self._initialize_engines()

    def _initialize_engines(self) -> None:
        """Initialize default engine configurations"""

        stealth_mode = resolve_mode(
            settings.ENGINE_STEALTH_MODE,
            ALLOWED_ENGINE_STEALTH_MODES,
            "both",
        )
        user_agent_mode = resolve_mode(
            settings.ENGINE_USER_AGENT_MODE,
            ALLOWED_ENGINE_USER_AGENT_MODES,
            "random",
        )
        ENGINES_TO_TEST_MODE = resolve_mode(
            settings.browser.mode,
            ALLOWED_ENGINES_TO_TEST_MODES,
            "both",
        )

        base_engines = [
            {
                "class": PlaywrightEngine,
                "params": {
                    "headless": True,
                    "name": "playwright-chrome",
                    "browser_type": "chromium",
                    "use_system_chrome": True,
                }
            },
            {
                "class": PlaywrightEngine,
                "params": {
                    "headless": True,
                    "name": "playwright-connect-over-cdp-chrome",
                    "browser_type": "chromium",
                    "use_system_chrome": True,
                    "connect_over_cdp": True,
                }
            },
            {
                "class": PlaywrightEngine,
                "params": {"headless": True, "name": "playwright-firefox", "browser_type": "firefox"}
            },
            {
                "class": CamoufoxEngine,
                "params": {"headless": True, "name": "camoufox"}
            },
            {
                "class": TfPlaywrightStealthEngine,
                "params": {"headless": True, "name": "tf-playwright-stealth-chromium",
                           "browser_type": "chromium"}
            },
            {
                "class": TfPlaywrightStealthEngine,
                "params": {"headless": True, "name": "tf-playwright-stealth-firefox", "browser_type": "firefox"}
            },
            {
                "class": PatchrightEngine,
                "params": {"headless": True, "name": "patchright"}
            },
            {
                "class": SeleniumEngine,
                "params": {"headless": True, "name": "selenium-chrome", "browser_type": "chrome"}
            },
            {
                "class": NoDriverEngine,
                "params": {"headless": True, "name": "nodriver-chrome", "browser_type": "chrome"}
            },
            {
                "class": ZenDriverEngine,
                "params": {"headless": True, "name": "zendriver-chrome", "browser_type": "chrome"}
            },
            {
                "class": SeleniumbaseEngine,
                "params": {"name": "seleniumbase-cdp-chrome"},
                "requires_display": True,
            },
            {
                "class": SeleniumBaseUCEngine,
                "params": {"headless": True, "name": "seleniumbase-uc-chrome"}
            },
            {
                "class": UlixeeHeroEngine,
                "params": {"headless": True, "name": "ulixee-hero"}
            },
            # {
            #     "class": NodePlaywrightEngine,
            #     "params": {
            #         "headless": True,
            #         "name": "node-playwright-chromium_headless",
            #         "browser_type": "chromium",
            #         "use_system_chrome": True,
            #     }
            # }
        ]

        engine_variants: List[Dict[str, Any]] = []

        for base_engine in base_engines:
            engine_cls = base_engine.get("class")
            base_params = dict(base_engine.get("params", {}))
            has_headless_flag = "headless" in base_params

            if has_headless_flag:
                if ENGINES_TO_TEST_MODE == "headless":
                    headless_modes = [True]
                elif ENGINES_TO_TEST_MODE == "headed":
                    headless_modes = [False]
                else:
                    headless_modes = [True, False]
            else:
                headless_modes = [None]

            for headless_value in headless_modes:
                params = dict(base_params)
                if headless_value is not None:
                    params["headless"] = headless_value

                # TfPlaywrightStealthEngine is inherently stealth; it only has stealth variants.
                if engine_cls is TfPlaywrightStealthEngine:
                    if stealth_mode == "no_stealth":
                        continue
                    stealth_variants = [True]
                else:
                    if stealth_mode == "use_stealth":
                        stealth_variants = [True]
                    elif stealth_mode == "no_stealth":
                        stealth_variants = [False]
                    else:
                        stealth_variants = [False, True]

                for with_stealth in stealth_variants:
                    variant_params = dict(params)
                    init_scripts = [
                        script
                        for script in variant_params.get("init_scripts", [])
                        if script not in STEALTH_INIT_SCRIPTS
                    ]

                    if with_stealth:
                        for script_name in STEALTH_INIT_SCRIPTS:
                            if script_name not in init_scripts:
                                init_scripts.append(script_name)

                    if init_scripts:
                        variant_params["init_scripts"] = init_scripts
                    else:
                        variant_params.pop("init_scripts", None)

                    variant_params["with_stealth"] = with_stealth
                    engine_variants.append({**base_engine, "params": variant_params})

        # Deduplicate variants that can overlap across expansion rules.
        unique_variants: List[Dict[str, Any]] = []
        seen_signatures: Set[str] = set()
        for engine in engine_variants:
            params = dict(engine.get("params", {}))
            init_scripts = params.get("init_scripts")
            if isinstance(init_scripts, list):
                params["init_scripts"] = sorted(init_scripts)
            signature = repr((engine.get("class"), sorted(params.items())))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_variants.append(engine)
        engine_variants = unique_variants

        if user_agent_mode == "random":
            for engine in engine_variants:
                params = engine.setdefault("params", {})
                if params.get("user_agent"):
                    continue

                browser_type = params.get("browser_type")
                engine_name = params.get("name")
                params["user_agent"] = generate_user_agent(browser_type, engine_name)
        else:
            for engine in engine_variants:
                engine.setdefault("params", {})

        for engine in engine_variants:
            params = engine.setdefault("params", {})
            _apply_engine_name_suffixes(engine.get("class"), params)

        has_display = bool(
            os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("MIR_SOCKET")
        )

        if has_display:
            self.engines.extend(engine_variants)
            return

        if settings.browser.try_headed_without_display:
            self.engines.extend(engine_variants)
            return

        # Headed browser variants require a display server and will fail in headless hosts.
        headless_compatible_engines = [
            engine
            for engine in engine_variants
            if not engine.get("requires_display", False)
            and engine.get("params", {}).get("headless", True)
        ]
        self.engines.extend(headless_compatible_engines)

    model_config = {"extra": "ignore"}


engines_config = EnginesSettings()
