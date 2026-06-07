#!/usr/bin/env python3
"""
Multi-instance DAMRU test: multiple tabs/pages in ONE Redroid container.

This demonstrates the marginal cost of additional instances when sharing
the Android OS (container stays the same, just more Chrome tabs).
"""
import asyncio
import logging
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

from damru.async_core import AsyncDamru
from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def get_container_memory_mb(container_id: str) -> int:
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container_id],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            mem_str = result.stdout.strip().split("/")[0].strip()
            if mem_str.endswith("MiB"):
                return int(float(mem_str.replace("MiB", "")))
            if mem_str.endswith("GiB"):
                return int(float(mem_str.replace("GiB", "")) * 1024)
    except Exception as e:
        logger.debug("Failed to get container memory: %s", e)
    return 0


def get_container_cpu_percent(container_id: str) -> float:
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", container_id],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            cpu_str = result.stdout.strip().replace("%", "")
            return float(cpu_str) if cpu_str else 0.0
    except Exception as e:
        logger.debug("Failed to get container CPU: %s", e)
    return 0.0


def find_damru_container() -> str | None:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=damru", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0][:12]
    except Exception:
        pass
    return None


async def test_multi_instance(num_tabs: int = 4):
    """Run multiple tabs in one DAMRU container and measure marginal cost."""
    logger.info("=" * 60)
    logger.info("MULTI-INSTANCE DAMRU TEST: %d tabs in one container", num_tabs)
    logger.info("=" * 60)

    damru = AsyncDamru(
        device="Google Pixel 8a",
        serial="127.0.0.1:5600",
        proxy=None,
        timezone="Europe/Berlin",
        locale="de-DE",
        chrome_package="com.android.chrome",
        restore_props=True,
        debug=False,
    )

    # Start the container + first Chrome
    logger.info("Starting DAMRU (container + first tab)...")
    start_time = time.time()
    context = await damru.__aenter__()
    startup_ms = (time.time() - start_time) * 1000
    logger.info("DAMRU started in %.0f ms", startup_ms)

    # Find container ID
    await asyncio.sleep(2)
    container_id = find_damru_container()
    if not container_id:
        logger.error("Could not find DAMRU container")
        await damru.__aexit__(None, None, None)
        return

    logger.info("Container ID: %s", container_id)

    # Measure baseline (1 tab)
    await asyncio.sleep(3)
    mem_1 = get_container_memory_mb(container_id)
    cpu_1 = get_container_cpu_percent(container_id)
    logger.info("Baseline (1 tab): memory=%d MB, cpu=%.1f%%", mem_1, cpu_1)

    # Create additional tabs
    pages = [context.pages[0]] if context.pages else []
    while len(pages) < num_tabs:
        page = await context.new_page()
        page.set_default_timeout(settings.browser.action_timeout_s * 1000)
        page.set_default_navigation_timeout(settings.browser.page_load_timeout_s * 1000)
        pages.append(page)
        logger.info("Created tab %d/%d", len(pages), num_tabs)

    # Navigate all tabs to a test page
    test_url = "https://httpbin.org/html"
    logger.info("Navigating all %d tabs to %s...", num_tabs, test_url)
    nav_start = time.time()
    nav_tasks = [page.goto(test_url, wait_until="domcontentloaded") for page in pages]
    await asyncio.gather(*nav_tasks, return_exceptions=True)
    nav_time = time.time() - nav_start
    logger.info("All navigations done in %.1fs", nav_time)

    await asyncio.sleep(3)
    mem_n = get_container_memory_mb(container_id)
    cpu_n = get_container_cpu_percent(container_id)
    logger.info("With %d tabs: memory=%d MB, cpu=%.1f%%", num_tabs, mem_n, cpu_n)

    # Calculate marginal cost
    marginal_mem = mem_n - mem_1
    marginal_per_tab = marginal_mem / (num_tabs - 1) if num_tabs > 1 else 0
    logger.info("=" * 60)
    logger.info("RESULTS:")
    logger.info("  Baseline (1 tab):      %d MB", mem_1)
    logger.info("  With %d tabs:           %d MB", num_tabs, mem_n)
    logger.info("  Marginal total:        %d MB", marginal_mem)
    logger.info("  Marginal per extra tab: %.0f MB", marginal_per_tab)
    logger.info("  CPU (1 tab):           %.1f%%", cpu_1)
    logger.info("  CPU (%d tabs):          %.1f%%", num_tabs, cpu_n)
    logger.info("=" * 60)

    # Cleanup
    await damru.__aexit__(None, None, None)
    logger.info("Test complete")


async def test_sequential_vs_parallel(num_tabs: int = 4):
    """Compare sequential vs parallel navigation in multi-tab setup."""
    logger.info("=" * 60)
    logger.info("SEQUENTIAL vs PARALLEL NAVIGATION TEST")
    logger.info("=" * 60)

    damru = AsyncDamru(
        device="Google Pixel 8a",
        serial="127.0.0.1:5600",
        proxy=None,
        timezone="Europe/Berlin",
        locale="de-DE",
        chrome_package="com.android.chrome",
        restore_props=True,
        debug=False,
    )

    context = await damru.__aenter__()
    await asyncio.sleep(2)

    container_id = find_damru_container()
    if not container_id:
        logger.error("Container not found")
        return

    # Create tabs
    pages = [context.pages[0]] if context.pages else []
    while len(pages) < num_tabs:
        pages.append(await context.new_page())

    test_urls = [
        "https://httpbin.org/html",
        "https://httpbin.org/robots.txt",
        "https://httpbin.org/headers",
        "https://httpbin.org/user-agent",
    ][:num_tabs]

    # Sequential
    logger.info("SEQUENTIAL navigation...")
    mem_before = get_container_memory_mb(container_id)
    seq_start = time.time()
    for i, (page, url) in enumerate(zip(pages, test_urls)):
        await page.goto(url, wait_until="domcontentloaded")
        logger.info("  Tab %d done", i + 1)
    seq_time = time.time() - seq_start
    mem_after_seq = get_container_memory_mb(container_id)

    # Parallel
    logger.info("PARALLEL navigation...")
    mem_before_par = get_container_memory_mb(container_id)
    par_start = time.time()
    await asyncio.gather(*[page.goto(url, wait_until="domcontentloaded") for page, url in zip(pages, test_urls)], return_exceptions=True)
    par_time = time.time() - par_start
    mem_after_par = get_container_memory_mb(container_id)

    logger.info("=" * 60)
    logger.info("Sequential: %.2fs (mem: %d -> %d MB)", seq_time, mem_before, mem_after_seq)
    logger.info("Parallel:   %.2fs (mem: %d -> %d MB)", par_time, mem_before_par, mem_after_par)
    logger.info("Speedup:    %.2fx", seq_time / par_time if par_time > 0 else 0)
    logger.info("=" * 60)

    await damru.__aexit__(None, None, None)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-instance DAMRU test")
    parser.add_argument("--tabs", type=int, default=4, help="Number of tabs")
    parser.add_argument("--test", choices=["marginal", "nav"], default="marginal", help="Test type")
    args = parser.parse_args()

    if args.test == "marginal":
        asyncio.run(test_multi_instance(args.tabs))
    else:
        asyncio.run(test_sequential_vs_parallel(args.tabs))