import os
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

STEALTH_INIT_SCRIPTS = ["stealth_improved.js"]
ALLOWED_ENGINE_STEALTH_MODES = {"no_stealth", "use_stealth", "both"}
ALLOWED_ENGINE_USER_AGENT_MODES = {"random", "native"}
ALLOWED_ENGINES_TO_TEST_MODES = {"headless", "headed", "both"}


def resolve_mode(value: str, allowed: Set[str], default: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else default


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

        # Build a single engine list and let ENV override behavior globally.
        # This avoids matrix-style duplication by stealth/headless modes.
        engine_variants: List[Dict[str, Any]] = [
            {**engine, "params": dict(engine.get("params", {}))}
            for engine in base_engines
        ]

        if stealth_mode == "no_stealth":
            engine_variants = [
                engine
                for engine in engine_variants
                if engine.get("class") is not TfPlaywrightStealthEngine
            ]

        for engine in engine_variants:
            params = engine.setdefault("params", {})

            if stealth_mode == "use_stealth":
                init_scripts = list(params.get("init_scripts", []))
                for script_name in STEALTH_INIT_SCRIPTS:
                    if script_name not in init_scripts:
                        init_scripts.append(script_name)
                params["init_scripts"] = init_scripts
            elif stealth_mode == "no_stealth":
                init_scripts = [x for x in params.get("init_scripts", []) if x not in STEALTH_INIT_SCRIPTS]
                if init_scripts:
                    params["init_scripts"] = init_scripts
                else:
                    params.pop("init_scripts", None)

            if ENGINES_TO_TEST_MODE in {"headless", "headed"} and "headless" in params:
                params["headless"] = ENGINES_TO_TEST_MODE == "headless"

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
