# Browsers Benchmark

A Python/Node.js benchmark suite for comparing browser automation engines against bot-protection, fingerprinting, timing, and resource-usage checks.

This repository is a fork of `techinz/browsers-benchmark`. The fork has evolved from the original proof-of-concept into a broader benchmark harness with more engines, proxy-aware runs, richer reports, and real experiment artifacts.

## Latest experiment

The latest full comparison currently included in the repository is:

`results/2026.03.05-camoufox-vs-cloak-full/summary.md`

Generated: **2026-03-05 08:06**

Engines compared:

| Engine | Privacy | Score | Performance | Windows/hour | Instances | Bottleneck | Full test s | Startup ms | Bypass % | Human % |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| `camoufox_headless` | 50.5 | 7,765.2 | 100.0 | 15,376.6 | 110 | RAM | 25.8 | 3,464.0 | 50.0 | 51.0 |
| `cloakbrowser_headless` | 48.9 | 7,231.4 | 96.1 | 14,783.1 | 96 | RAM | 23.4 | 1,662.0 | 62.5 | 35.3 |

Key observations from this run:

- `camoufox_headless` had the highest total score and the best measured performance in this run.
- `cloakbrowser_headless` had a higher bypass rate, but lower human-likeness and a lower final score.
- Both engines were RAM-bound at the tested concurrency level.
- Both engines received a low reCAPTCHA score of `0.10`, so this benchmark should be treated as a comparative measurement rather than a claim that either engine is universally production-ready.
- Fingerprint demo suspect scores were `8%` for `camoufox_headless` and `29%` for `cloakbrowser_headless`.

Reports include Markdown summaries plus dashboards for bypass rate, timings, resource usage, reCAPTCHA, browser smart signals, Incolumitas, DeviceAndBrowserInfo, and fingerprint scans.

## What changed in this fork

Compared with the original upstream repository, this fork adds and changes the following areas:

- Added and refreshed engine integrations, including Camoufox, CloakBrowser, Playwright/Patchright-style engines, SeleniumBase, Nodriver/Zendriver, and Ulixee Hero experiments.
- Added proxy-aware benchmark execution with per-engine proxy assignment, retry limits, fallback behavior, and proxy state reset at benchmark start.
- Added environment-driven configuration via `.env.example` for timeouts, workers, retries, proxy mode, engine mode, repeat count, and engine run limits.
- Added more complete benchmark result generation: JSON output, Markdown summaries, visual dashboards, timing charts, bypass charts, resource charts, and fingerprint-specific sections.
- Added fingerprint demo data collection and reporting for navigator fields, browser smart signals, Incolumitas, DeviceAndBrowserInfo, and scan-fingerprint outputs.
- Added overall score tooling and a Makefile wrapper for install/test/start/status/stop/score workflows.
- Added test coverage and CI workflow scaffolding for the benchmark code and proxy behavior.
- Added a version marker and refreshed example report assets.
- Removed private host/user/IP details from the public history so the fork can be published safely.

## Repository layout

- `main.py` — benchmark entry point.
- `engines/` — browser automation engine implementations.
- `utils/` — reporting, metrics, screenshots, retry helpers, process helpers, and browser data utilities.
- `tests/` — pytest tests and engine/proxy checks.
- `results/` — generated benchmark outputs and report examples.
- `documents/` — local input documents such as proxy lists; real private proxy lists should not be committed.
- `.env.example` — safe configuration template.

## Requirements

- Python 3.10+
- Node.js/npm for Node-backed engines
- Linux environment recommended for full benchmark runs
- Browser/runtime dependencies required by the selected engines
- Optional proxy list when `PROXY_ENABLED=true`

Install Python dependencies:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Install Node dependencies:

```bash
npm install
```

Or use the project installer when appropriate:

```bash
make install
```

## Configuration

Copy `.env.example` to `.env` and adjust values for your test environment.

Important settings:

```env
PROXY_ENABLED=true
PROXY_FILE_PATH=documents/proxies.txt
PROXY_MAX_RETRIES=3
PROXY_FALLBACK_MAX_RETRIES=3
PAGE_LOAD_TIMEOUT_S=90
PAGE_STABILIZATION_DELAY_S=5
ENGINES_TO_TEST_MODE=both
BROWSER_TRY_HEADED_WITHOUT_DISPLAY=false
CAMOUFOX_UNLOCK_SHADOW_DOM=true
NUM_WORKERS_MIN=1
NUM_WORKERS_MAX=10
BENCHMARK_REPEAT_COUNT=1
ENGINE_MAX_ATTEMPTS=30
ENGINE_RUN_TIMEOUT_S=5400
MAX_RETRIES=3
```

Proxy files can contain full proxy URLs such as:

```text
http://username:password@host:port
```

Do not commit real proxy credentials, server names, local usernames, private IPs, public IPs, API keys, cookies, or raw logs from private infrastructure.

## Running

Start a benchmark in the foreground:

```bash
./venv/bin/python main.py
```

Start it in the background through the Makefile:

```bash
make start
make status
make stop
```

Run tests:

```bash
make test-fast
```

Run engine tests:

```bash
make test
```

Build or inspect overall scores:

```bash
make score
```

## Results

Each run writes structured outputs under `results/`:

- `benchmark_results.json`
- `summary.md`
- raw browser/fingerprint JSON files
- logs
- PNG dashboards under `media/`

The current README is based on the latest full comparison in `results/2026.03.05-camoufox-vs-cloak-full/summary.md`.

## Public-safety notes

Before publishing this fork, the repository history was rewritten to redact the private host/user/IP strings that were present in generated artifacts and metadata. The public tree should still be reviewed before adding new generated results, because benchmark logs often contain environment-specific values.

## License

MIT. See `LICENSE`.
