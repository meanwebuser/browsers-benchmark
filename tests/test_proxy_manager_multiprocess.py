import multiprocessing as mp
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from utils.proxy.proxy_manager import ProxyManager


class FastProxyManager(ProxyManager):
    async def _test_proxy_async(self, proxy_url: str) -> bool:
        # Avoid external network in unit tests.
        return True


def _worker_get_proxy(
    start_event: mp.Event,
    proxies_file: str,
    db_path: str,
    output_queue: mp.Queue,
    supported_protocols: list[str],
) -> None:
    manager = FastProxyManager(proxies_file=proxies_file, db_path=db_path)
    start_event.wait(timeout=5)
    proxy = manager.get_proxy_by_protocol(supported_protocols, site=f"worker-{os.getpid()}")
    output_queue.put(proxy)


def _build_manager() -> tuple[tempfile.TemporaryDirectory[str], Path, Path, list[str], FastProxyManager]:
    temp_dir = tempfile.TemporaryDirectory()
    tmp_path = Path(temp_dir.name)
    proxies_file = tmp_path / "proxies.txt"
    db_path = tmp_path / "proxies.db"

    proxy_urls = [
        "http://10.0.0.1:8001",
        "http://10.0.0.2:8002",
        "http://10.0.0.3:8003",
    ]
    proxies_file.write_text("\n".join(proxy_urls), encoding="utf-8")

    manager = FastProxyManager(
        proxies_file=str(proxies_file),
        db_path=str(db_path),
    )
    return temp_dir, proxies_file, db_path, proxy_urls, manager


def _set_selected_at(db_path: Path, proxy_url: str, dt: datetime) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE proxies SET selected_at = ? WHERE url = ?",
            (dt.isoformat(timespec="seconds"), proxy_url),
        )


def test_returns_oldest_used_proxy_first() -> None:
    temp_dir, _, db_path, proxy_urls, manager = _build_manager()
    try:
        now = datetime.utcnow()
        # Oldest usage should be selected first.
        _set_selected_at(db_path, proxy_urls[0], now - timedelta(minutes=5))
        _set_selected_at(db_path, proxy_urls[1], now - timedelta(minutes=30))
        _set_selected_at(db_path, proxy_urls[2], now - timedelta(minutes=10))

        selected = manager.get_proxy_by_protocol(["http"], site="oldest-used")

        assert selected is not None
        assert selected["url"] == proxy_urls[1]
    finally:
        temp_dir.cleanup()


def test_multiprocess_does_not_return_same_proxy() -> None:
    temp_dir, proxies_file, db_path, _, _ = _build_manager()
    try:
        start_event = mp.Event()
        output_queue: mp.Queue = mp.Queue()

        processes = [
            mp.Process(
                target=_worker_get_proxy,
                args=(
                    start_event,
                    str(proxies_file),
                    str(db_path),
                    output_queue,
                    ["http"],
                ),
            )
            for _ in range(2)
        ]

        for process in processes:
            process.start()

        start_event.set()

        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)

        for process in processes:
            assert process.exitcode == 0

        results = [output_queue.get(timeout=2) for _ in processes]

        assert all(result is not None for result in results)
        urls = [result["url"] for result in results]
        assert len(urls) == len(set(urls))
    finally:
        temp_dir.cleanup()
