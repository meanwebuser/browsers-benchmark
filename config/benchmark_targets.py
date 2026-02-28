from typing import List, Dict, Callable, Optional

from pydantic import BaseModel, Field

from utils.targets.browser_data.deviceandbrowserinfo import extract_deviceandbrowserinfo_data
from utils.targets.browser_data.fingerprint_demo import extract_fingerprint_demo_data
from utils.targets.browser_data.scan_fingerprint import extract_scan_fingerprint_data
from utils.targets.browser_data.incolumitas import extract_incolumitas_data
from utils.targets.browser_data.ipify import extract_ipify_data
from utils.targets.browser_data.recaptcha_score import extract_recaptcha_score
from utils.targets.check_bypass.amazon import check_amazon_bypass
from utils.targets.check_bypass.cloudflare_protected import check_cloudflare_bypass
from utils.targets.check_bypass.datadome_protected import check_datadome_bypass
from utils.targets.check_bypass.datadome_protected_2 import check_datadome2_bypass
from utils.targets.check_bypass.google_search import check_google_search_bypass
from utils.targets.check_bypass.ticketmaster import check_ticketmaster_bypass
from utils.targets.check_bypass.yandex_search import check_yandex_search_bypass
from utils.targets.check_bypass.page_loaded import check_page_loaded_bypass


class Target(BaseModel):
    """Configuration for a test target"""

    name: str = Field(..., description="Target name")
    url: str = Field(..., description="Target URL")
    check_function: str = Field(..., description="Function name to check the target")
    search_query_param: Optional[str] = Field(
        None, description="Optional query parameter to override with a random search phrase"
    )
    search_language: Optional[str] = Field(
        None, description="Language key used to pick search words for random queries"
    )
    description: str = Field(default="", description="Target description")

    model_config = {"extra": "ignore"}


class BypassTargetsSettings(BaseModel):
    """Configuration for bypass targets"""

    targets: List[Target] = Field(
        default_factory=lambda: [
            Target(
                name="google_search",
                url="https://www.google.com/search?q=what+is+my+user+agent",
                check_function="check_google_search_bypass",
                search_query_param="q",
                search_language="en",
                description="Google Search bypass test"
            ),
            Target(
                name="yandex_search",
                url="https://ya.ru/search/?text=what+is+my+user+agent",
                check_function="check_yandex_search_bypass",
                search_query_param="text",
                search_language="ru",
                description="Yandex Search bypass test"
            ),
            Target(
                name="cloudflare_protected",
                url="https://community.cloudflare.com",
                check_function="check_cloudflare_bypass",
                description="Cloudflare protection bypass test"
            ),
            Target(
                name="proxy5_cloudflare",
                url="https://proxy5.net/user/clientarea.php?action=services",
                check_function="check_cloudflare_bypass",
                description="Proxy5 Cloudflare bypass test"
            ),
            # Target(# TOO many false positive
            #     name="datadome_protected",
            #     url="https://datadome.co/customers-stories/",
            #     check_function="check_datadome_bypass",
            #     description="DataDome protection bypass test"
            # ),
            Target(
                name="amazon_product",
                url="https://a.co/d/21FTKNR",
                check_function="check_amazon_bypass",
                description="Amazon captcha bypass test"
            ),
            Target(
                name="wildberries_search",
                url="https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%B1%D0%BE%D0%BB%D1%8C%D1%88%D0%B8%D0%B5%20%D0%B3%D0%BE%D1%80%D0%BE%D0%B4%D0%B0",
                check_function="check_page_loaded_bypass",
                description="Wildberries search bypass test",
                search_query_param="search",
                search_language="ru",
            ),
            Target(
                name="ozon_search",
                url="https://www.ozon.ru/search/?text=%D0%B1%D0%BE%D0%BB%D1%8C%D1%88%D0%B8%D0%B5+%D0%B3%D0%BE%D1%80%D0%BE%D0%B4%D0%B0&from_global=true",
                check_function="check_page_loaded_bypass",
                description="Ozon search bypass test",
                search_query_param="text",
                search_language="ru",
            ),
            Target(
                name="avito_real_estate_search",
                url="https://www.avito.ru/moskva/nedvizhimost?context=H4sIAAAAAAAA_5ySwZKiPBSF38Vtby6h1R969RuHTKg0XaTLmLAzoUtiAXZJIOrUvPtUWp1Zz-xyq-Dc75x7dmmU_hjSCNKZOZ5OH8bZYz97GdLF4r90RntnaJcdatJOuvX2rfXWxKKvkLjWmbcs87aSjdckG5XknxrNDT18GupwA-xUTo78D0yW7n1dDo6swntI8BPDYcYemN8Di_k-wQhYXA54XU4Ow-M9FjiW3zf-lXzzoGK-d_gZ1GYftIeC4IceqK9v54EvMBlybhQSrtrOQWK6kDhvVJegStyZibjutvUoOnEx6I83hZKL6cTNr40aTcTl4VOTdtzFRfCnPyJvTSfO9faWw1vIqc-iSubz2z72m-vmZ2WoPRvanSeFMthtk_F9ww09HNHr1aBivUrCjpqI5y-91lvIJ35w-AxszQ-XdTmGvBQrXY2vwJZ8X4Qskrtu1Nakmar7vzURQyVXk-m5oT0M_85bNDURvY7z-Z33Wvy1j9ADvAQ2BfYFKB1u9RRuPBahH8t7F8KMI4npIHHuKsmPGvFbn3reaiK8jnOQOE-kBDt7-fkrAAD__-87Af-9AgAA&localPriority=0&q=%D0%B3%D0%BE%D1%80%D0%BE%D0%B4%D0%B0",
                check_function="check_page_loaded_bypass",
                description="Avito real estate search bypass test",
                search_query_param="search",
                search_language="ru",
            ),
            # Target(
            #     name="ticketmaster",
            #     url="https://www.ticketmaster.com/",
            #     check_function="check_ticketmaster_bypass",
            #     description="Ticketmaster (Imperva) bypass test"
            # ),
        ]
    )

    checkers: Dict[str, Callable] = Field(
        default_factory=lambda: {
            "check_google_search_bypass": check_google_search_bypass,
            "check_yandex_search_bypass": check_yandex_search_bypass,
            "check_cloudflare_bypass": check_cloudflare_bypass,
            "check_datadome_bypass": check_datadome_bypass,
            "check_amazon_bypass": check_amazon_bypass,
            "check_ticketmaster_bypass": check_ticketmaster_bypass,
            "check_page_loaded_bypass": check_page_loaded_bypass,
        }
    )

    model_config = {"extra": "ignore"}


class BrowserDataTargetsSettings(BaseModel):
    """Configuration for browser data extraction targets"""

    targets: List[Target] = Field(
        default_factory=lambda: [
            Target(
                name="recaptcha_score",
                url="https://antcpt.com/score_detector",
                check_function="extract_recaptcha_score",
                description="reCAPTCHA v3 score extraction"
            ),
            Target(
                name="fingerprint_demo",
                url="https://fingerprint.com/demo/",
                check_function="extract_fingerprint_demo_data",
                description="Fingerprint.com Browser Smart Signals extraction"
            ),
            Target(
                name="incolumitas",
                url="https://bot.incolumitas.com/#browserData",
                check_function="extract_incolumitas_data",
                description="Incolumitas browser data extraction"
            ),
            Target(
                name="deviceandbrowserinfo",
                url="https://deviceandbrowserinfo.com/are_you_a_bot",
                check_function="extract_deviceandbrowserinfo_data",
                description="DeviceAndBrowserInfo 'Are you a bot' extraction"
            ),
            Target(
                name="scan_fingerprint",
                url="https://fingerprint-scan.com/",
                check_function="extract_scan_fingerprint_data",
                description="Fingerprint Scan bot risk score extraction"
            )
        ]
    )

    checkers: Dict[str, Callable] = Field(
        default_factory=lambda: {
            "extract_recaptcha_score": extract_recaptcha_score,
            "extract_fingerprint_demo_data": extract_fingerprint_demo_data,
            "extract_ipify_data": extract_ipify_data,
            "extract_incolumitas_data": extract_incolumitas_data,
            "extract_deviceandbrowserinfo_data": extract_deviceandbrowserinfo_data,
            "extract_scan_fingerprint_data": extract_scan_fingerprint_data
        }
    )

    model_config = {"extra": "ignore"}


class BenchmarkTargetsSettings(BaseModel):
    """Benchmark targets configuration"""

    bypass_targets: BypassTargetsSettings = Field(default_factory=BypassTargetsSettings)
    browser_data_targets: BrowserDataTargetsSettings = Field(default_factory=BrowserDataTargetsSettings)

    model_config = {"extra": "ignore"}


benchmark_targets_config = BenchmarkTargetsSettings()
