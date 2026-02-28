import asyncio
import gc
import inspect
import logging
import os
import random
import re
import secrets
import shutil
from datetime import datetime
from time import monotonic
from typing import Dict, List, Any, Optional
import multiprocessing as mp
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import psutil


from config.benchmark_targets import benchmark_targets_config
from config.engines import engines_config
from config.settings import settings
from engines.base import BrowserEngine
from utils.dataclasses import BypassTestResult, BrowserDataResult, BenchmarkResults, MetricSummary
from utils.io import create_directory_structure, save_results
from utils.logging.logging import setup_logging
from utils.metrics import calculate_metrics, calculate_min_mean_max
from utils.proxy.proxy_manager import (
    proxy_manager,
    is_proxy_related_error,
    handle_proxy_fallback,
    get_external_ip,
)
from utils.report import generate_report
from utils.screenshot import take_screenshot

setup_logging(engine_name="main")

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LANGUAGE = "en"

SEARCH_WORDS = {
    "en": [
        "weather",
        "science",
        "travel",
        "coding",
        "history",
        "music",
        "books",
        "kitchen",
        "football",
        "finance",
        "space",
        "health",
        "art",
        "education",
        "innovation",
        "astronomy",
        "architecture",
        "wellness",
    ],
    "ru": [
        "погода",
        "наука",
        "путешествие",
        "кодирование",
        "история",
        "музыка",
        "книги",
        "кухня",
        "футбол",
        "финансы",
        "космос",
        "здоровье",
        "искусство",
        "образование",
        "инновация",
        "астрономия",
    ],
    "es": [
        "clima",
        "ciencia",
        "viajes",
        "programación",
        "historia",
        "música",
        "libros",
        "cocina",
        "fútbol",
        "finanzas",
        "espacio",
        "salud",
        "arte",
        "tecnología",
        "educación",
    ],
}


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _build_intermediate_report(
        result_path: str,
        total_tasks: int,
        completed_tasks: int,
        completed_engines: int,
        failed_engines: int,
        benchmark_started_at: float,
        pending_count: int,
        stage: str = "in_progress",
) -> None:
    """Generate a progress snapshot and refresh summary from current partial results."""
    elapsed = monotonic() - benchmark_started_at
    eta = "unknown"
    if completed_tasks > 0:
        rate = completed_tasks / max(elapsed, 1e-6)
        remaining = total_tasks - completed_tasks
        eta = _format_duration(remaining / rate) if rate > 0 else "unknown"

    progress_pct = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0.0
    progress_file = os.path.join(result_path, "progress_report.txt")
    results_file = os.path.join(result_path, "benchmark_results.json")

    with open(progress_file, "w", encoding="utf-8") as f:
        f.write(f"Stage: {stage}\n")
        f.write(f"Updated at: {datetime.now().isoformat()}\n")
        f.write(f"Progress: {completed_tasks}/{total_tasks} ({progress_pct:.1f}%)\n")
        f.write(f"Success: {completed_engines}\n")
        f.write(f"Failed: {failed_engines}\n")
        f.write(f"Running: {pending_count}\n")
        f.write(f"Elapsed: {_format_duration(elapsed)}\n")
        f.write(f"ETA: {eta}\n")
        f.write(f"Results JSON: {results_file}\n")

    if os.path.exists(results_file):
        try:
            generate_report(results_file, result_path)
            logger.info(f"Intermediate report updated: {progress_file}")
        except Exception as e:
            logger.error(f"Failed to generate intermediate report: {e}")
    else:
        logger.info("Intermediate report skipped: benchmark_results.json is not available yet")


def _generate_random_search_phrase(words_count: int = 3, language: str = DEFAULT_SEARCH_LANGUAGE) -> str:
    language = language if language in SEARCH_WORDS else DEFAULT_SEARCH_LANGUAGE
    words = [random.choice(SEARCH_WORDS[language]) for _ in range(max(1, words_count))]
    words.append(secrets.token_hex(2))
    return " ".join(words)


def _resolve_target_url(target: Dict[str, Any]) -> str:
    target_url = target["url"]
    query_param = target.get("search_query_param")
    if not query_param:
        return target_url

    language = target.get("search_language") or DEFAULT_SEARCH_LANGUAGE

    parsed = urlparse(target_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[query_param] = [_generate_random_search_phrase(language=language)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


async def collect_peak_resources(
        engine: BrowserEngine,
        stop_event: asyncio.Event,
        sample_interval_s: float = 0.2
) -> tuple[int, float]:
    """
    Collect peak memory and max CPU while the caller-controlled window is active.
    """

    peak_rss_mb = 0
    max_cpu_percent = 0.0

    while not stop_event.is_set():
        memory_mb = int(await asyncio.to_thread(engine.get_memory_usage))
        cpu_percent = float(await asyncio.to_thread(engine.get_cpu_usage))

        if memory_mb > peak_rss_mb:
            peak_rss_mb = memory_mb
        if cpu_percent > max_cpu_percent:
            max_cpu_percent = cpu_percent

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sample_interval_s)
        except asyncio.TimeoutError:
            continue

    return peak_rss_mb, max_cpu_percent


async def test_bypass_target(
        engine: BrowserEngine,
        target: Dict[str, Any],
        screenshots_path: str
) -> BypassTestResult:
    """
    Test a single bypass target

    :param engine: The browser engine to use
    :param target: The target configuration to test
    :param screenshots_path: Path to save screenshots
    """

    logger.info(f"Testing {engine.name} against {target['name']}...")

    target_url = _resolve_target_url(target)
    result = BypassTestResult(target=target["name"], url=target_url)
    test_started_at = monotonic()

    async def attempt_bypass_test():
        monitoring_stop_event = asyncio.Event()
        monitor_task = asyncio.create_task(collect_peak_resources(engine, monitoring_stop_event))

        try:
            navigation_result = await engine.navigate(target_url)
            result.performance.load_time_ms = int(navigation_result.get("load_time", 0) * 1000)

            check_function = benchmark_targets_config.bypass_targets.checkers.get(target["check_function"])
            if check_function is None:
                raise ValueError(f"Check function '{target['check_function']}' not found")

            await asyncio.sleep(settings.browser.page_stabilization_delay_s)  # wait for page to stabilize

            result.performance.memory_mb = int(engine.get_memory_usage())
            result.performance.cpu_percent = engine.get_cpu_usage()
            result.bypass = await check_function(engine)
        finally:
            monitoring_stop_event.set()
            peak_rss_mb, max_cpu_percent = await monitor_task
            result.performance.peak_rss_mb = max(result.performance.memory_mb, peak_rss_mb)
            result.performance.max_cpu_percent = max(result.performance.cpu_percent, max_cpu_percent)

        return result

    try:
        result = await attempt_bypass_test()
        if settings.proxy.enabled and getattr(engine, "proxy", None):
            proxy_manager.mark_proxy_success(engine.proxy, site=target["name"])
    except Exception as e:
        # check if this is a proxy-related error that warrants fallback
        if is_proxy_related_error(e) and settings.proxy.enabled:
            fallback_result, error_msg = await handle_proxy_fallback(
                engine, target['name'], e, attempt_bypass_test
            )
            if fallback_result:
                result = fallback_result
            else:
                result.error = error_msg
        else:
            # non-proxy error - just record it
            result.error = str(e)
            if settings.proxy.enabled and getattr(engine, "proxy", None):
                proxy_manager.mark_proxy_error(
                    engine.proxy,
                    error_message=str(e),
                    site=target["name"],
                    mark_failed=False
                )
            logger.warning(f'{engine.name} failed bypass test for {target["name"]}: {e}')
    finally:
        result.performance.test_duration_ms = int((monotonic() - test_started_at) * 1000)

    await take_screenshot(engine, screenshots_path, target["name"])

    return result


async def extract_browser_data(
        engine: BrowserEngine,
        target: Dict[str, Any],
        screenshots_path: str
) -> BrowserDataResult:
    """
    Extract browser data from a target

    :param engine: The browser engine to use
    :param target: The target configuration to extract data from
    :param screenshots_path: Path to save screenshots
    """

    logger.info(f"Extracting browser data from {target['name']} using {engine.name}...")

    target_url = _resolve_target_url(target)
    result = BrowserDataResult(target=target["name"], url=target_url)
    test_started_at = monotonic()

    async def attempt_data_extraction():
        navigation_result = await engine.navigate(target_url)
        result.navigation_time_ms = int(navigation_result.get("load_time", 0) * 1000)
        await asyncio.sleep(settings.browser.page_stabilization_delay_s)  # ensure page is fully loaded

        extract_function = benchmark_targets_config.browser_data_targets.checkers.get(target["check_function"])
        if extract_function is None:
            raise ValueError(f"Extract function '{target['check_function']}' not found")

        target_data = await extract_function(engine)

        # update result with extracted data
        for key, value in target_data.items():
            if hasattr(result, key):
                setattr(result, key, value)

        return result

    try:
        result = await attempt_data_extraction()
        if settings.proxy.enabled and getattr(engine, "proxy", None):
            proxy_manager.mark_proxy_success(engine.proxy, site=target["name"])
    except Exception as e:
        # check if this is a proxy-related error that warrants fallback
        if is_proxy_related_error(e) and settings.proxy.enabled:
            fallback_result, error_msg = await handle_proxy_fallback(
                engine, target['name'], e, attempt_data_extraction
            )
            if fallback_result:
                result = fallback_result
            else:
                result.error = error_msg
        else:
            # non-proxy error, just record it
            result.error = str(e)
            if settings.proxy.enabled and getattr(engine, "proxy", None):
                proxy_manager.mark_proxy_error(
                    engine.proxy,
                    error_message=str(e),
                    site=target["name"],
                    mark_failed=False
                )
            logger.warning(f'{engine.name} failed data extraction for {target["name"]}: {e}')
    finally:
        result.test_duration_ms = int((monotonic() - test_started_at) * 1000)

    await take_screenshot(engine, screenshots_path, target["name"])

    return result


async def run_benchmark_for_engine(
        engine_cls,
        engine_params: Dict[str, Any],
        bypass_targets: List[Dict[str, Any]],
        browser_data_targets: List[Dict[str, Any]],
        screenshots_path: str,
        proxy: Optional[Dict[str, str]] = None,
        direct_external_ip: Optional[str] = None,
) -> BenchmarkResults | None:
    """
    Run benchmark for a browser engine

    :param engine_cls: The browser engine class to instantiate
    :param engine_params: Parameters for the engine
    :param bypass_targets: List of bypass targets to test
    :param browser_data_targets: List of browser data targets to test
    :param screenshots_path: Path for saving screenshots
    :param proxy: Optional proxy configuration to use for the engine
    :param direct_external_ip: Known direct external IP resolved in main process
    """

    if proxy:
        engine_params = {**engine_params, "proxy": proxy}

    engine = engine_cls(**engine_params)
    engine.known_direct_external_ip = direct_external_ip
    engine.run_result_path = os.path.dirname(os.path.dirname(screenshots_path))  # results/<timestamp>
    engine_screenshots_path = os.path.join(screenshots_path, engine.name)

    if os.path.exists(engine_screenshots_path):
        shutil.rmtree(engine_screenshots_path, ignore_errors=True)  # clear previous data if exists

    os.makedirs(engine_screenshots_path, exist_ok=True)

    results = BenchmarkResults(
        engine=engine.name,
        timestamp=datetime.now().isoformat()
    )

    memory_readings: List[int] = []
    cpu_readings: List[float] = []
    peak_memory_readings: List[int] = []
    max_cpu_readings: List[float] = []

    try:
        startup_started_at = monotonic()
        await engine.start()
        results.startup_time_ms = int((monotonic() - startup_started_at) * 1000)
        logger.info(f"Started {engine.name} engine")
        # warm up psutil CPU counters once right after process start to avoid a cold first sample
        await asyncio.to_thread(engine.get_cpu_usage)

        # test bypass targets
        for target in bypass_targets:
            bypass_result = await test_bypass_target(engine, target, engine_screenshots_path)
            results.bypass_targets_results.append(bypass_result)

            if not bypass_result.error:
                memory_readings.append(bypass_result.performance.memory_mb)
                cpu_readings.append(bypass_result.performance.cpu_percent)
                peak_memory_readings.append(bypass_result.performance.peak_rss_mb)
                max_cpu_readings.append(bypass_result.performance.max_cpu_percent)

            await asyncio.sleep(1)

        # extract browser data
        for target in browser_data_targets:
            data_result = await extract_browser_data(engine, target, engine_screenshots_path)
            results.browser_data_targets_results.append(data_result)
            await asyncio.sleep(1)
    except Exception as e:
        logger.exception(f"Critical error during benchmark for {engine.name}: {e}")
        results.error = str(e)
    finally:
        # calculate final metrics
        avg_memory, avg_cpu, bypass_rate = calculate_metrics(
            results.bypass_targets_results, memory_readings, cpu_readings
        )
        results.average_memory_mb = avg_memory
        results.average_cpu_percent = avg_cpu
        mem_min, mem_mean, mem_max = calculate_min_mean_max([float(value) for value in memory_readings])
        cpu_min, cpu_mean, cpu_max = calculate_min_mean_max(cpu_readings)
        peak_mem_min, peak_mem_mean, peak_mem_max = calculate_min_mean_max(
            [float(value) for value in peak_memory_readings]
        )
        max_cpu_min, max_cpu_mean, max_cpu_max = calculate_min_mean_max(max_cpu_readings)

        results.memory_mb_stats = MetricSummary(min=mem_min, mean=mem_mean, max=mem_max)
        results.cpu_percent_stats = MetricSummary(min=cpu_min, mean=cpu_mean, max=cpu_max)
        results.peak_rss_mb_stats = MetricSummary(
            min=peak_mem_min,
            mean=peak_mem_mean,
            max=peak_mem_max,
        )
        results.max_cpu_percent_stats = MetricSummary(
            min=max_cpu_min,
            mean=max_cpu_mean,
            max=max_cpu_max,
        )
        results.bypass_rate = bypass_rate

        # cleanup
        try:
            await engine.stop()
            logger.info(f"Stopped {engine.name} engine")
        except Exception as e:
            logger.error(f"Error stopping engine {engine.name}: {e}")
        finally:
            if settings.proxy.enabled and getattr(engine, "proxy", None):
                proxy_manager.release_proxy_lock(engine.proxy)

    return results





def run_engine_worker(task):
    """
    Функция, выполняемая в отдельном процессе.
    task: кортеж (engine_cls, engine_params, proxy, supported_protocols, bypass_targets, browser_data_targets, screenshots_path, result_path, direct_external_ip)
    """
    engine_cls, engine_params, proxy, supported_protocols, bypass_targets, browser_data_targets, screenshots_path, result_path, direct_external_ip = task
    engine_name = engine_params["name"]
    process_name = f"engine-{engine_name}"
    try:
        mp.current_process().name = process_name
    except Exception:
        pass

    safe_engine_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", engine_name)
    worker_log_file = os.path.join(result_path, "logs", f"{safe_engine_name}.log")
    setup_logging(log_file=worker_log_file, engine_name=engine_name)
    logger = logging.getLogger(f"worker.{engine_name}")
    
    # Переопределяем функцию run_benchmark_for_engine, чтобы она использовала переданный proxy
    # (оригинальная функция уже принимает proxy, передадим его)
    import asyncio

    # Создаём event loop для asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        if settings.proxy.enabled and not proxy:
            if supported_protocols:
                proxy = proxy_manager.get_proxy_by_protocol(supported_protocols, site=engine_name)
                if not proxy:
                    logger.error(f"No compatible proxy available for {engine_name}, skipping...")
                    return None
                logger.info(f"Assigned {proxy['protocol']} proxy to {engine_name}")
            else:
                logger.warning(
                    f"Engine {engine_name} does not support any proxy protocols, running without proxy"
                )

        results = loop.run_until_complete(
            run_benchmark_for_engine(
                engine_cls=engine_cls,
                engine_params=engine_params,
                bypass_targets=bypass_targets,
                browser_data_targets=browser_data_targets,
                screenshots_path=screenshots_path,
                proxy=proxy,
                direct_external_ip=direct_external_ip,
            )
        )
        if results:
            # Сохраняем результаты
            results_path = save_results(results, result_path)
            logger.info(f"Results saved to {results_path}")
        return results
    except Exception as e:
        logger.error(f"Unhandled exception in worker: {e}")
        return None
    finally:
        loop.close()

        # Worker processes can be reused by the pool.
        # Ensure no browser subprocesses leak into the next task.
        try:
            worker_proc = psutil.Process(os.getpid())
            children = worker_proc.children(recursive=True)
            if children:
                for child in children:
                    try:
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                _, alive = psutil.wait_procs(children, timeout=3)
                for child in alive:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
        except Exception as cleanup_error:
            logger.debug("Worker process cleanup failed: %s", cleanup_error)


def run_parallel_benchmarks() -> None:
    """Запуск бенчмарков параллельно для всех движков"""
    direct_external_ip = None
    repeat_count = max(1, settings.BENCHMARK_REPEAT_COUNT)
    # Проверка прокси (как в оригинале)
    if not settings.proxy.enabled:
        logger.warning("PROXIES ARE DISABLED! Results may be inaccurate due to IP reputation.")
    else:
        direct_external_ip = get_external_ip(timeout=settings.proxy.test_timeout)
        if direct_external_ip:
            logger.info(f"Resolved direct external IP once in main: {direct_external_ip}")
        else:
            logger.warning("Could not resolve direct external IP in main. Engines will fallback to local lookup.")

        # проверяем, хватает ли прокси для всех движков
        engines_with_protocols = []
        for engine_config in engines_config.engines:
            engine_cls = engine_config["class"]
            temp_engine = engine_cls(**engine_config["params"])
            engines_with_protocols.append((
                engine_config['params']['name'],
                temp_engine.supported_proxy_protocols
            ))
        if not proxy_manager.validate_proxy_count_by_protocol(engines_with_protocols):
            logger.error("PROXY VALIDATION FAILED! Not enough compatible proxies.")
            raise Exception("Not enough compatible proxies for the configured engines!")
        engines_requiring_proxy = [name for name, protocols in engines_with_protocols if protocols]
        required_proxy_count = len(engines_requiring_proxy) * repeat_count
        if not proxy_manager.validate_proxy_count(required_proxy_count):
            logger.error(
                "PROXY VALIDATION FAILED! Not enough proxies for repeats: "
                f"required={required_proxy_count}, repeat_count={repeat_count}"
            )
            raise Exception("Not enough proxies for the configured BENCHMARK_REPEAT_COUNT")

    # Создаём структуру каталогов
    timestamp = datetime.now().strftime("%Y.%m.%d %H:%M")
    result_path, media_path, screenshots_path = create_directory_structure(timestamp)

    # Подготавливаем общие данные для всех движков
    bypass_targets = [target.model_dump() for target in benchmark_targets_config.bypass_targets.targets]
    browser_data_targets = [target.model_dump() for target in benchmark_targets_config.browser_data_targets.targets]

    # Формируем список задач (каждая задача = один запуск движка)
    task_specs = []
    # Build task specs in waves: all engines run1, then all engines run2, etc.
    for run_idx in range(1, repeat_count + 1):
        for engine_config in engines_config.engines:
            base_engine_name = engine_config["params"]["name"]
            temp_engine = engine_config["class"](**engine_config["params"])
            supported_protocols = temp_engine.supported_proxy_protocols
            run_engine_name = (
                f"{base_engine_name}__run{run_idx}" if repeat_count > 1 else base_engine_name
            )
            run_engine_params = {**engine_config["params"], "name": run_engine_name}
            task_specs.append({
                "engine_cls": engine_config["class"],
                "engine_params": run_engine_params,
                "run_engine_name": run_engine_name,
                "supported_protocols": supported_protocols,
            })

    tasks = []
    for idx, spec in enumerate(task_specs):
        tasks.append((
            spec["engine_cls"],
            spec["engine_params"],
            None,
            spec["supported_protocols"],
            bypass_targets,
            browser_data_targets,
            screenshots_path,
            result_path,
            direct_external_ip,
        ))

    if not tasks:
        logger.error("No engines to run after proxy assignment.")
        return

    # Определяем число воркеров = cpu_count // 2, но в диапазоне NUM_WORKERS_MIN..NUM_WORKERS_MAX
    workers_min = max(1, settings.NUM_WORKERS_MIN)
    workers_max = max(workers_min, settings.NUM_WORKERS_MAX)
    num_workers = min(workers_max, max(workers_min, mp.cpu_count() // 2))
    logger.info(f"Starting parallel benchmark with {num_workers} workers for {len(tasks)} engine runs")

    # Запускаем пул процессов
    total_tasks = len(tasks)
    progress_heartbeat_s = 30
    benchmark_started_at = monotonic()

    executor_kwargs = {"max_workers": num_workers}
    if "max_tasks_per_child" in inspect.signature(ProcessPoolExecutor).parameters:
        executor_kwargs["max_tasks_per_child"] = 1
        logger.info("Process pool isolation enabled: max_tasks_per_child=1")
    else:
        logger.warning(
            "ProcessPoolExecutor in this Python version does not support max_tasks_per_child; "
            "worker reuse remains enabled."
        )

    with ProcessPoolExecutor(**executor_kwargs) as executor:
        # Запускаем все задачи и собираем результаты по мере завершения
        future_to_engine = {executor.submit(run_engine_worker, task): task[1]['name'] for task in tasks}
        future_started_at = {future: monotonic() for future in future_to_engine}
        completed_engines = 0
        failed_engines = 0
        completed_tasks = 0

        logger.info(
            f"Overall progress: {completed_tasks}/{total_tasks} (0.0%) | "
            f"elapsed=00:00:00 | eta=unknown | running={total_tasks}"
        )
        _build_intermediate_report(
            result_path=result_path,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            completed_engines=completed_engines,
            failed_engines=failed_engines,
            benchmark_started_at=benchmark_started_at,
            pending_count=total_tasks,
            stage="started",
        )

        pending_futures = set(future_to_engine.keys())
        while pending_futures:
            done_futures, pending_futures = wait(
                pending_futures,
                timeout=progress_heartbeat_s,
                return_when=FIRST_COMPLETED,
            )

            if not done_futures:
                elapsed = monotonic() - benchmark_started_at
                eta = "unknown"
                if completed_tasks > 0:
                    rate = completed_tasks / max(elapsed, 1e-6)
                    remaining = total_tasks - completed_tasks
                    eta = _format_duration(remaining / rate) if rate > 0 else "unknown"

                progress_pct = (completed_tasks / total_tasks) * 100
                logger.info(
                    f"Overall progress: {completed_tasks}/{total_tasks} ({progress_pct:.1f}%) | "
                    f"success={completed_engines} failed={failed_engines} | "
                    f"elapsed={_format_duration(elapsed)} | eta={eta} | "
                    f"running={len(pending_futures)}"
                )
                _build_intermediate_report(
                    result_path=result_path,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    completed_engines=completed_engines,
                    failed_engines=failed_engines,
                    benchmark_started_at=benchmark_started_at,
                    pending_count=len(pending_futures),
                )
                continue

            for future in done_futures:
                engine_name = future_to_engine[future]
                completed_tasks += 1
                engine_elapsed = monotonic() - future_started_at.get(future, benchmark_started_at)
                try:
                    result = future.result()
                    if result:
                        completed_engines += 1
                        logger.info(
                            f"Benchmark for {engine_name} completed successfully "
                            f"in {_format_duration(engine_elapsed)}"
                        )
                    else:
                        failed_engines += 1
                        logger.error(
                            f"Benchmark for {engine_name} returned no result "
                            f"after {_format_duration(engine_elapsed)}"
                        )
                except Exception as e:
                    failed_engines += 1
                    logger.error(
                        f"Benchmark for {engine_name} failed with exception "
                        f"after {_format_duration(engine_elapsed)}: {e}"
                    )

            elapsed = monotonic() - benchmark_started_at
            eta = "unknown"
            if completed_tasks > 0:
                rate = completed_tasks / max(elapsed, 1e-6)
                remaining = total_tasks - completed_tasks
                eta = _format_duration(remaining / rate) if rate > 0 else "unknown"

            progress_pct = (completed_tasks / total_tasks) * 100
            logger.info(
                f"Overall progress: {completed_tasks}/{total_tasks} ({progress_pct:.1f}%) | "
                f"success={completed_engines} failed={failed_engines} | "
                f"elapsed={_format_duration(elapsed)} | eta={eta} | "
                f"running={len(pending_futures)}"
            )
            _build_intermediate_report(
                result_path=result_path,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                completed_engines=completed_engines,
                failed_engines=failed_engines,
                benchmark_started_at=benchmark_started_at,
                pending_count=len(pending_futures),
            )

    # Генерируем единый отчёт в конце выполнения
    results_file = os.path.join(result_path, "benchmark_results.json")
    summary_file = os.path.join(result_path, "summary.md")
    final_report_file = os.path.join(result_path, "final_report.txt")
    if os.path.exists(results_file):
        try:
            generate_report(results_file, result_path)
            logger.info(f"Report generated: {summary_file}")
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")

        with open(final_report_file, "w", encoding="utf-8") as f:
            f.write(f"Benchmark finished at: {datetime.now().isoformat()}\n")
            f.write(f"Engines completed: {completed_engines}/{len(tasks)}\n")
            f.write(f"Results JSON: {results_file}\n")
            f.write(f"Summary report: {summary_file}\n")
        logger.info(f"Final report file saved to: {final_report_file}")
        _build_intermediate_report(
            result_path=result_path,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            completed_engines=completed_engines,
            failed_engines=failed_engines,
            benchmark_started_at=benchmark_started_at,
            pending_count=0,
            stage="finished",
        )
    else:
        logger.warning("Results JSON was not found. Final report file was not created.")

    # После завершения всех воркеров выводим статистику прокси (как в оригинале)
    if settings.proxy.enabled:
        proxy_stats = proxy_manager.get_stats()
        logger.info("\n===== PROXY STATISTICS =====")
        logger.info(f"Total proxies loaded: {proxy_stats['total_loaded']}")
        logger.info(f"Proxies used: {proxy_stats['used']}")
        logger.info(f"Proxies failed: {proxy_stats['failed']}")
        logger.info(f"Proxies remaining: {proxy_stats['available']}")
        if proxy_stats['failed'] > 0:
            logger.warning(f"{proxy_stats['failed']} proxies failed during benchmarking")
        if proxy_stats['available'] == 0 and proxy_stats['failed'] > 0:
            logger.warning("All proxies have been exhausted or failed")

    # Финальная очистка (как в оригинале)
    gc.collect()


def main() -> None:
    try:
        # run_all_benchmarks()  // заменяем на параллельную версию
        run_parallel_benchmarks()
    except KeyboardInterrupt:
        logger.info("Benchmark interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")
        raise


if __name__ == "__main__":
    # Необходимо для корректной работы multiprocessing на Windows
    main()
