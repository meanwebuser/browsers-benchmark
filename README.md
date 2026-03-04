# Browser Engine Benchmark

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A toolkit for testing browser automation engines against modern web protection systems. It checks how well each engine can bypass bot detection and measures their speed, resource usage, and resistance to fingerprinting.

<i>(Need some help with <b>Automation</b>? You can  <a href="https://t.me/autogrami">hire me</a> for custom development or consulting!)</i>

---

## Release 0.2.0 (February 28, 2026)

This release refreshes the report visuals and documents the current version so the sample output matches the new styling.

### Changes

- Applied a consistent Seaborn "talk" theme in `utils/report/visualizations.py` (soft background, unified fonts, subtle grids, and updated notes) to make the dashboard and charts look more polished.
- Regenerated `results/example/summary.md` plus all `results/example/media/*.png` assets so the sample report directly reflects the new look and new fingerprint/browser detection sections.
- Added a new `VERSION` marker that records the release number for future reference.

---

## 🎯 Overview
Modern web applications use advanced bot detection like Cloudflare, DataDome, and Imperva to block automated access. This benchmark suite shows how different browser automation engines handle these defenses:
- **Bypass Success Rate**: Effectiveness against major protection systems
- **Performance Metrics**: Memory usage, CPU consumption, and page load times
- **Fingerprinting Resistance**: reCAPTCHA scores and CreepJS trust ratings
- **Network Analysis**: IP detection (proxy validation) and WebRTC leak testing

## 🚀 Key Features
### Protection System Testing
- **Cloudflare** 
- **DataDome**   
- **Amazon** 
- **Google Search** 
- **Ticketmaster (Imperva)**
- <i>More systems coming soon</i>

### Browser Engine Support
- <a href="https://playwright.dev">**Playwright**</a> - Microsoft's automation framework (Chrome, Firefox, Safari)
- <a href="https://camoufox.com">**Camoufox**</a> - Playwright-based
- <a href="https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python">**Patchright**</a> - Playwright-based
- <a href="https://github.com/tinyfish-io/tf-playwright-stealth">**Playwright Stealth**</a> - Playwright-based
- <a href="https://www.selenium.dev">**Selenium**</a> - Open-source browser automation framework (tested without proxies)
- <a href="https://seleniumbase.io/">**Seleniumbase**</a> - Open-source professional toolkit for web automation activities
- <a href="https://github.com/ultrafunkamsterdam/nodriver">**NoDriver**</a> - Open-source browser automation framework (supports only SOCKS5 proxies)
- <a href="https://github.com/cdpdriver/zendriver">**ZenDriver**</a> - NoDriver-based
- <a href="https://playwright.dev/docs/intro#using-playwright-in-javascript--typescript">**Node Playwright**</a> - Node.js Playwright worker-based engine
- <i>More engines coming soon. What engine should I add next?</i>

### Analytics
- Automated report generation with visualizations
- Performance profiling and resource usage tracking
- Exportable results in JSON and Markdown formats

## 🔒 **Important: Proxy Requirements**
**Using a clean proxy is essential for accurate benchmark results.**
<details>
<summary>Why Proxies Are Required</summary>

- **IP Reputation**: Your home/datacenter IP may already be flagged by protection systems from previous automation attempts, browser extensions, or security software
- **Clean Testing Environment**: A fresh proxy IP ensures you're testing the browser engine's capabilities, not your IP's reputation
- **Rate Limiting**: Repeated tests from the same IP can trigger rate limiting, affecting bypass success rates
</details>

## 📊 Sample Results
This benchmark provides detailed comparative analysis. Here's an excerpt from a recent test run (more in <a href="results/example">results/example</a>):  
<i>Real IP in this example - 149.102.240.75</i>  
<i>Proxy IP in this example is different for each engine</i>

### Overall Bypass Rate
| Engine | Bypass Rate (%) |
|-----------------|----------------:|
| camoufox_headless | 83.3 |
| nodriver-chrome | 83.3 |
| playwright-firefox | 83.3 |
| camoufox | 66.7 |
| patchright | 66.7 |
| playwright-firefox_headless | 66.7 |
| zendriver-chrome_headless | 50.0 |
| tf-playwright-stealth-firefox_headless | 50.0 |
| tf-playwright-stealth-chromium_headless | 50.0 |
| tf-playwright-stealth-chromium | 50.0 |
| seleniumbase-cdp-chrome | 50.0 |
| nodriver-chrome_headless | 33.3 |
| tf-playwright-stealth-firefox | 33.3 |
| selenium-chrome__no_proxy | 33.3 |
| playwright-chrome_headless | 33.3 |
| zendriver-chrome | 33.3 |
| playwright-chrome | 16.7 |
| patchright_headless | 16.7 |
| selenium-chrome_headless__no_proxy | 16.7 |


### Resource Usage Comparison
| Engine | Memory Usage (MB) | CPU Usage (%) |
|-----------------|------------------:|--------------:|
| playwright-chrome_headless | 212.0 | 4.9 |
| tf-playwright-stealth-chromium_headless | 298.0 | 9.4 |
| selenium-chrome_headless__no_proxy | 354.0 | 11.5 |
| zendriver-chrome | 364.0 | 10.2 |
| seleniumbase-cdp-chrome | 375.0 | 14.0 |
| zendriver-chrome_headless | 424.0 | 13.4 |
| playwright-chrome | 454.0 | 20.2 |
| tf-playwright-stealth-chromium | 462.0 | 19.8 |
| selenium-chrome__no_proxy | 519.0 | 15.5 |
| nodriver-chrome_headless | 547.0 | 20.0 |
| nodriver-chrome | 554.0 | 19.0 |
| patchright_headless | 560.0 | 12.6 |
| playwright-firefox_headless | 606.0 | 28.1 |
| tf-playwright-stealth-firefox | 659.0 | 26.4 |
| patchright | 709.0 | 19.2 |
| tf-playwright-stealth-firefox_headless | 822.0 | 46.2 |
| camoufox | 1007.0 | 43.5 |
| playwright-firefox | 1012.0 | 51.7 |
| camoufox_headless | 1037.0 | 45.5 |


### Recaptcha Scores - https://antcpt.com/score_detector
| Engine | Recaptcha Score (0-1) |
|-----------------|--------------------:|
| patchright | 0.30 |
| camoufox | 0.10 |
| camoufox_headless | 0.10 |
| patchright_headless | 0.10 |
| playwright-chrome | 0.10 |
| playwright-firefox | 0.10 |
| playwright-firefox_headless | 0.10 |
| seleniumbase-cdp-chrome | 0.10 |
| tf-playwright-stealth-chromium | 0.10 |
| tf-playwright-stealth-chromium_headless | 0.10 |
| tf-playwright-stealth-firefox | 0.10 |
| tf-playwright-stealth-firefox_headless | 0.10 |
| nodriver-chrome | nan |
| nodriver-chrome_headless | nan |
| playwright-chrome_headless | nan |
| selenium-chrome__no_proxy | nan |
| selenium-chrome_headless__no_proxy | nan |
| zendriver-chrome | nan |
| zendriver-chrome_headless | nan |

Note 1: "nan" indicates no score was obtained - the website just stopped working when tests were run

Note 2: `
This Score is taken by solving the reCAPTCHA v3 on your browser.
The Score shows if Google considers you as HUMAN or BOT.
1.0 is very likely a good interaction, 0.0 is very likely a bot
With low score values (< 0.3) you'll get a slow reCAPTCHA 2, it would be hard to solve it.
And vise versa, with score >= 0.7 it will be much easier. 
`



### Visual Dashboard
![Bypass Dashboard](results/example/media/bypass_dashboard.png)

### Recaptcha Score Visualization
![Recaptcha Scores](results/example/media/recaptcha_scores.png)

### CreepJS Visualization
![CreepJS Scores](results/example/media/creepjs_scores.png)

## 🛠️ Installation
Tested only on Ubuntu. Mac have some trubles with camoufox and etc. 
### Quick Start
1. **Clone the repository**
   ```bash
   git clone https://github.com/megamen32/browsers-benchmark.git
   cd browsers-benchmark
   ```

2[Auto]. **Set up Python environment**
   ```bash
   chmod +x install.sh
   bash install.sh
   ```

2[Manual]. **Install browser engines**

   **Playwright**
   ```bash
   playwright install
   # On Linux also run:
   playwright install-deps
   ```

   **Camoufox**
   ```bash
   # Windows
   camoufox fetch
   
   # Linux  
   python -m camoufox fetch
   sudo apt install -y libgtk-3-0 libx11-xcb1 libasound2
   ```

   **Patchright**
   ```bash
   patchright install chromium
   ```

   **Ulixee Hero**
   ```bash
   npm install
   ```

4. **Configure settings**
   ```bash
   cp .env.example .env
   # Edit .env with your proxy settings if needed
   ```

5. **Configure proxies**
   1. Create a file named `proxies.txt` in the `documents` directory.
   2. Add your proxy URLs in format `http://username:password@proxy_host:port` or `http://proxy_host:port`.  
      ❗️ IMPORTANT (1): Number of proxies has to be not less than number of engines you want to test.  
      ❗️ IMPORTANT (2): Some engines support different proxy protocols - for example, Playwright supports only HTTP and HTTPS, but NoDriver supports only SOCKS5.  
         This implies that you have to add multiple proxy protocols to the `proxies.txt` file or exclude some engines from the test.  
         At the moment you need all HTTP/HTTPS proxies and at least 1 SOCKS5 for NoDriver. Also, the benchmark will show you what proxy protocols are missing.  
      ❗️ IMPORTANT (3): Selenium won't use any proxies.  

   Example `proxies.txt` content (each line is a separate proxy):
   ```
   http://proxy1.example.com:8080
   http://proxy2.example.com:8080
   http://username:password@proxy3.example.com:8080
   http://username:password@proxy4.example.com:8080
   socks5://username:password@proxy5.example.com:8080
   ```

6. **Run benchmark**
   ```bash
   python main.py
   ```

7. **Run tests (pytest, single framework)**
   ```bash
   make test
   ```

   Engine diagnostics are available as opt-in pytest tests:
   ```bash
   make test-engines
   ```

   Under the hood these cover:
   - `tests/test_stealth_python_params.py` - validates Python -> stealth navigator params per engine
   - `tests/test_proxy_env.py` - validates proxy usage per engine
   - `tests/test_headed_xvfb_env.py` - validates headed launch behavior in headless env (Xvfb fallback)

## ⚙️ Configuration

### Environment Variables (.env)
```bash
# Proxy Configuration (highly recommended to enable)
PROXY_ENABLED=true
PROXY_FILE_PATH=documents/proxies.txt
PROXY_MAX_RETRIES=3
PROXY_FALLBACK_MAX_RETRIES=3
ENGINE_MAX_ATTEMPTS=30

# Performance Settings
PAGE_LOAD_TIMEOUT_S=90
PAGE_STABILIZATION_DELAY_S=5
ENGINES_TO_TEST_MODE=both
BROWSER_TRY_HEADED_WITHOUT_DISPLAY=false
ENGINE_RUN_TIMEOUT_S=5400
NUM_WORKERS_MIN=1
NUM_WORKERS_MAX=10
BENCHMARK_REPEAT_COUNT=1
MAX_RETRIES=3
```

## 📈 Output & Reports

The benchmark generates reports in the `results/` directory:

- **`summary.md`** - Human-readable markdown report
- **`benchmark_results.json`** - Raw data for further analysis  
- **`media/`** - Generated visualizations and screenshots
  - `bypass_dashboard.png` - Multi-metric dashboard
  - `recaptcha_scores.png` - reCAPTCHA performance chart
  - `creepjs_scores.png` - Fingerprinting resistance analysis
  - `screenshots` - Screenshots of all tested targets

### Privacy vs Performance Score Helper

Use `build_overall_score.py` to calculate two axes per engine from `benchmark_results.json`:
- **Privacy score**: combines bypass rate and bot-detection signals.
- **Performance score**: based on estimated parallel browser instances and page startup speed (`windows/hour`).

By default, it picks the latest valid run from `results/`:

```bash
python build_overall_score.py
```

Use custom hardware limits (optional):

```bash
python build_overall_score.py --cpu-count 16 --ram-gb 64
```

Limit scoring to specific targets:

```bash
python build_overall_score.py --sites google_search cloudflare_protected recaptcha_score scan_fingerprint
```

Save computed axes as JSON:

```bash
python build_overall_score.py --output-file results/overall_axes.json
```

## 🏗️ Architecture

The codebase follows a modular architecture for extensibility:

```
├── config/           # Configuration management
├── engines/          # Browser engine implementations  
├── tests/            # Standalone engine diagnostics
├── utils/
│   ├── targets/      # Test target definitions
│   ├── report/       # Report generation system
│   ├── logging/      # Structured logging
│   └── ...
└── results/          # Output directory
```

### Adding New Targets
1. Modify `config/benchmark_targets.py` to add custom test targets:

    ```python
    Target(
        name="custom_site",
        url="https://example.com",
        check_function="check_custom_bypass",
        description="Custom site protection test"
    )
    ```
2. Create a check function for the target in `utils/targets/check_bypass`, for example in a file named `custom_bypass.py`:
    ```python
    from engines.base import BrowserEngine

    async def check_custom_bypass(engine: BrowserEngine) -> bool:
        element_found, element_html = await engine.locator('//div[@class="captcha"]')

        return not element_found # no captcha found - success!
    ```
3. Add it to the checkers mapping in `config/benchmark_targets.py`'s `BypassTargetsSettings`:
    ```python
    checkers: Dict[str, Callable] = Field(
        default_factory=lambda: {
            "check_cloudflare_bypass": check_cloudflare_bypass,
            "check_datadome_bypass": check_datadome_bypass,
            ...
            "check_custom_bypass": check_custom_bypass,
        }
    )
    ```

### Adding New Engines
1. Extend the `BrowserEngine` base class:

   ```python  
   class CustomEngine(BrowserEngine):
       async def start(self) -> None:
           # Initialize browser
           
       async def navigate(self, url: str) -> Dict[str, Any]:
           # Navigation logic
   ```
   
   Or, if Playwright-based, extend `PlaywrightBase` base class:
   ```python  
   class CustomPlaywrightBasedEngine(PlaywrightBase):
       ...
   ```
   
    Or, if Selenium-based, extend `SeleniumBase` base class:
   ```python  
   class CustomSeleniumBasedEngine(SeleniumBase):
       ...
   ```
   
2. Add it to the engines mapping in `config/engines.py`'s `EnginesSettings`:
    ```python
    base_engines = [
            {
                "class": PlaywrightEngine,
                "params": {"headless": True, "name": "playwright-chrome_headless", "browser_type": "chromium"}
            },
            ...
            {
                "class": CustomEngine,
                "params": {"headless": True, "name": "custom_engine", "browser_type": "chromium"}
            }
   ]
    ```

## 🔧 Platform-Specific Notes
### Troubleshooting

**Common Issues:**
- **Detection failures**: Verify proxy configuration and target accessibility

## 🤝 Contributing

Contributions are welcome! Areas where help is needed:
- **New Protection Systems**: Add support for additional bot detection services
- **Browser Engines**: Implement support for new automation frameworks (e.g. Selenium-based)
- **Analysis Tools**: Enhance reporting and visualization

## 📝 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer
This tool is designed for educational and research purposes. Users are responsible for ensuring compliance with website terms of service and applicable laws. The authors and contributors do not encourage or endorse any malicious use of this software.
