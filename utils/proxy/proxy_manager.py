import asyncio
import logging
import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from config.settings import settings
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def get_external_ip(proxy_url: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    """
    Get external IP via Ipify.

    :param proxy_url: Optional proxy URL for the request
    :param timeout: Request timeout in seconds
    :return: IP string or None if failed
    """
    ipify_url = "https://api.ipify.org?format=json"
    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = client.get(ipify_url)
            response.raise_for_status()

        ip = response.json().get("ip")
        return ip if isinstance(ip, str) and ip.strip() else None
    except Exception as error:
        logger.debug(
            "Failed to get %s external IP%s: %s",
            "proxied" if proxy_url else "direct",
            f" via {proxy_url}" if proxy_url else "",
            error,
        )
        return None


async def get_external_ip_async(proxy_url: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    """
    Async variant of get_external_ip via Ipify.

    :param proxy_url: Optional proxy URL for the request
    :param timeout: Request timeout in seconds
    :return: IP string or None if failed
    """
    ipify_url = "https://api.ipify.org?format=json"

    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = await client.get(ipify_url)
            response.raise_for_status()

        ip = response.json().get("ip")
        return ip if isinstance(ip, str) and ip.strip() else None
    except Exception as error:
        logger.debug(
            "Failed to get %s external IP%s: %s",
            "proxied" if proxy_url else "direct",
            f" via {proxy_url}" if proxy_url else "",
            error,
        )
        return None


def test_proxy(proxy_url: str, test_url: str = "http://httpbin.org/ip", timeout: int = 10) -> bool:
    """Sync proxy check retained for compatibility."""
    try:
        with httpx.Client(proxy=proxy_url, timeout=timeout, trust_env=False) as client:
            response = client.get(test_url)
            if response.status_code == 200:
                logger.debug(f"Proxy {proxy_url} works. Response: {response.text}")
                return True
            logger.debug(f"Proxy {proxy_url} returned status code {response.status_code}")
            return False
    except Exception as error:
        logger.debug(f"Proxy {proxy_url} failed: {error}")
        return False


async def test_proxy_async(proxy_url: str, test_url: str = "http://httpbin.org/ip", timeout: int = 10) -> bool:
    """Async proxy check using httpx with SOCKS support (httpx[socks])."""
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout, trust_env=False) as client:
            response = await client.get(test_url)
            if response.status_code == 200:
                logger.debug(f"Proxy {proxy_url} works. Response: {response.text}")
                return True
            logger.debug(f"Proxy {proxy_url} returned status code {response.status_code}")
            return False
    except Exception as error:
        logger.debug(f"Proxy {proxy_url} failed: {error}")
        return False


def is_proxy_related_error(error: Exception) -> bool:
    """
    Determine if an error is proxy-related and warrants a proxy fallback

    :param error: Exception object to check
    :return: True for proxy/network errors, False for other errors
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    proxy_error_patterns = [
        "connection", "connect", "refused", "timeout", "timed out",
        "proxy", "authentication", "unauthorized", "407",
        "err_proxy_connection_failed", "proxy_connection_failed",
        "network", "dns", "resolve", "unreachable",
        "net::", "err_", "failed to navigate", "navigation timeout",
        "err_timed_out", "err_connection_refused", "err_network_changed",
        "webdriver", "selenium", "chrome not reachable", "firefox not responding",
        "session not created", "unknown error", "chrome failed to start",
        "502", "503", "504", "bad gateway", "service unavailable", "gateway timeout",
    ]
    network_error_types = [
        "timeouterror", "networkerror", "browsererror",
        "webdriverexception", "sessionnotcreatedexception", "timeoutexception",
    ]

    for pattern in proxy_error_patterns:
        if pattern in error_str:
            logger.debug(f"Identified proxy-related error pattern: '{pattern}' in '{error_str}'")
            return True

    if error_type in network_error_types:
        logger.debug(f"Identified proxy-related error type: '{error_type}'")
        return True

    if "timeout" in error_type or "connection" in error_type:
        logger.debug(f"Identified proxy-related error type: '{error_type}'")
        return True

    logger.debug(f"Error not identified as proxy-related: {error_type} - {error_str}")
    return False


class ProxyManager:
    def __init__(
        self,
        proxies_file: str = settings.proxy.file_path,
        db_path: str = settings.proxy.db_path,
    ):
        self.proxies_file = proxies_file
        self.db_path = db_path
        self.test_url = settings.proxy.test_url
        self.test_timeout = settings.proxy.test_timeout
        self.lock_stale_s = settings.proxy.lock_stale_s
        self.process_id = os.getpid()

        self._ensure_db()
        self.cleanup_stale_locks()
        self._load_proxies()

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @staticmethod
    def _is_process_alive(pid: Optional[int]) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _ensure_db(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    protocol TEXT,
                    host TEXT,
                    port TEXT,
                    username TEXT,
                    password TEXT,
                    is_failed INTEGER NOT NULL DEFAULT 0,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    selected_at TEXT,
                    last_success_at TEXT,
                    last_error_at TEXT,
                    last_error TEXT,
                    locked_at TEXT,
                    locked_by INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proxy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    site TEXT,
                    error_message TEXT,
                    process_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(proxy_id) REFERENCES proxies(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proxies_protocol ON proxies(protocol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proxies_failed ON proxies(is_failed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proxies_locked ON proxies(locked_by)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_proxy ON proxy_events(proxy_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_site ON proxy_events(site)")
            conn.execute("DROP INDEX IF EXISTS idx_proxies_host_unique")

    def _parse_proxy(self, proxy_url: str) -> Optional[Dict[str, str]]:
        try:
            raw = proxy_url.strip()
            if not raw:
                return None

            # Accept host:port lines without protocol by inferring a sane default.
            if "://" not in raw:
                host_port = raw.rsplit(":", 1)
                inferred_protocol = "http"
                if len(host_port) == 2:
                    try:
                        port = int(host_port[1])
                        if port in {1080, 1085, 9050}:
                            inferred_protocol = "socks5"
                    except ValueError:
                        pass
                raw = f"{inferred_protocol}://{raw}"

            parsed = urlparse(raw)
            protocol = (parsed.scheme or "").lower()
            if protocol == "socks5h":
                protocol = "socks5"
            if protocol not in {"http", "https", "socks5"}:
                logger.warning("Skipping proxy with unsupported protocol: %s", proxy_url)
                return None
            if not parsed.hostname:
                logger.warning("Skipping proxy with invalid host: %s", proxy_url)
                return None

            port = parsed.port
            if not port:
                port = 1080 if protocol == "socks5" else 8080

            auth_prefix = ""
            if parsed.username and parsed.password:
                auth_prefix = f"{parsed.username}:{parsed.password}@"

            normalized_url = f"{protocol}://{auth_prefix}{parsed.hostname}:{port}"
            proxy_config = {
                "protocol": protocol,
                "host": parsed.hostname,
                "port": str(port),
                "url": normalized_url,
            }
            if parsed.username and parsed.password:
                proxy_config["username"] = parsed.username
                proxy_config["password"] = parsed.password
            return proxy_config
        except Exception as error:
            logger.error(f"Failed to parse proxy URL {proxy_url}: {error}")
            return None

    def _load_proxies(self) -> None:
        if not os.path.exists(self.proxies_file):
            logger.warning(f"Proxies file {self.proxies_file} not found")
            return

        try:
            with open(self.proxies_file, "r", encoding="utf-8") as file:
                proxies = [line.strip() for line in file if line.strip() and not line.startswith("#")]
        except Exception as error:
            logger.error(f"Failed to load proxies from {self.proxies_file}: {error}")
            return

        now = self._now_iso()
        loaded_count = 0
        invalid_count = 0

        with self._connect() as conn:
            for proxy_url in proxies:
                parsed = self._parse_proxy(proxy_url)
                if not parsed:
                    invalid_count += 1
                    continue

                try:
                    conn.execute(
                        """
                        INSERT INTO proxies(url, protocol, host, port, username, password, created_at, updated_at)
                        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(url) DO UPDATE SET
                            protocol=excluded.protocol,
                            host=excluded.host,
                            port=excluded.port,
                            username=excluded.username,
                            password=excluded.password,
                            updated_at=excluded.updated_at
                        """,
                        (
                            parsed["url"],
                            parsed["protocol"],
                            parsed["host"],
                            parsed["port"],
                            parsed.get("username"),
                            parsed.get("password"),
                            now,
                            now,
                        ),
                    )
                    loaded_count += 1
                except sqlite3.IntegrityError:
                    invalid_count += 1

        logger.info(
            "Loaded %s proxies into DB from %s (skipped invalid/duplicate: %s)",
            loaded_count,
            self.proxies_file,
            invalid_count,
        )

    def _record_event(
        self,
        conn: sqlite3.Connection,
        proxy_id: int,
        event_type: str,
        site: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO proxy_events(proxy_id, event_type, site, error_message, process_id, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (proxy_id, event_type, site, error_message, self.process_id, self._now_iso()),
        )

    async def _test_proxy_async(self, proxy_url: str) -> bool:
        return await test_proxy_async(proxy_url, test_url=self.test_url, timeout=self.test_timeout)

    @staticmethod
    def _run_async(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError("Sync proxy API called from async context. Use async proxy methods instead.")

    def _get_proxy_by_url(self, conn: sqlite3.Connection, proxy_url: str) -> Optional[sqlite3.Row]:
        return conn.execute("SELECT * FROM proxies WHERE url = ?", (proxy_url,)).fetchone()

    def _mark_proxy_error(
        self,
        proxy_url: str,
        error_message: str,
        site: Optional[str] = None,
        mark_failed: bool = False,
    ) -> None:
        now = self._now_iso()
        with self._connect() as conn:
            proxy_row = self._get_proxy_by_url(conn, proxy_url)
            if not proxy_row:
                return

            conn.execute(
                """
                UPDATE proxies
                SET error_count = error_count + 1,
                    last_error_at = ?,
                    last_error = ?,
                    is_failed = CASE WHEN ? THEN 1 ELSE is_failed END,
                    locked_at = CASE WHEN ? THEN NULL ELSE locked_at END,
                    locked_by = CASE WHEN ? THEN NULL ELSE locked_by END,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, error_message, 1 if mark_failed else 0, 1 if mark_failed else 0, 1 if mark_failed else 0, now, proxy_row["id"]),
            )
            self._record_event(conn, proxy_row["id"], "error", site=site, error_message=error_message)

    def _mark_proxy_success(self, proxy_url: str, site: Optional[str] = None) -> None:
        now = self._now_iso()
        with self._connect() as conn:
            proxy_row = self._get_proxy_by_url(conn, proxy_url)
            if not proxy_row:
                return

            conn.execute(
                """
                UPDATE proxies
                SET success_count = success_count + 1,
                    last_success_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, proxy_row["id"]),
            )
            self._record_event(conn, proxy_row["id"], "success", site=site)

    def _select_candidate(
        self,
        conn: sqlite3.Connection,
        supported_protocols: Optional[List[str]] = None,
    ) -> Optional[sqlite3.Row]:
        supported_protocols = supported_protocols or []

        query = """
            SELECT p.*
            FROM proxies p
            JOIN (
                SELECT
                    host,
                    MAX(selected_at) AS host_last_selected
                FROM proxies
                WHERE is_failed = 0
                GROUP BY host
            ) hp ON hp.host = p.host
            WHERE p.is_failed = 0
              AND p.locked_by IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM proxies locked
                  WHERE locked.host = p.host
                    AND locked.locked_by IS NOT NULL
              )
        """
        params: List[str] = []

        if supported_protocols:
            placeholders = ",".join(["?"] * len(supported_protocols))
            query += f" AND p.protocol IN ({placeholders})"
            params.extend(supported_protocols)

        query += """
            ORDER BY
                CASE WHEN hp.host_last_selected IS NULL THEN 0 ELSE 1 END ASC,
                hp.host_last_selected ASC,
                p.id ASC
            LIMIT 1
        """
        return conn.execute(query, params).fetchone()

    def _count_available(self, supported_protocols: Optional[List[str]] = None) -> int:
        supported_protocols = supported_protocols or []
        with self._connect() as conn:
            query = """
                SELECT COUNT(DISTINCT p.host) AS cnt
                FROM proxies p
                WHERE p.is_failed = 0
                  AND p.locked_by IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM proxies locked
                      WHERE locked.host = p.host
                        AND locked.locked_by IS NOT NULL
                  )
            """
            params: List[str] = []
            if supported_protocols:
                placeholders = ",".join(["?"] * len(supported_protocols))
                query += f" AND p.protocol IN ({placeholders})"
                params.extend(supported_protocols)
            row = conn.execute(query, params).fetchone()
            return int(row["cnt"]) if row else 0

    def _try_lock_proxy(self, conn: sqlite3.Connection, proxy_id: int, site: Optional[str] = None) -> bool:
        now = self._now_iso()
        result = conn.execute(
            """
            UPDATE proxies AS p
            SET locked_at = ?,
                locked_by = ?,
                selected_at = ?,
                use_count = use_count + 1,
                updated_at = ?,
                is_failed = 0
            WHERE p.id = ?
              AND p.locked_by IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM proxies locked
                  WHERE locked.host = p.host
                    AND locked.locked_by IS NOT NULL
              )
            """,
            (now, self.process_id, now, now, proxy_id),
        )
        if result.rowcount == 1:
            self._record_event(conn, proxy_id, "selected", site=site)
            return True
        return False

    def _row_to_proxy_config(self, row: sqlite3.Row) -> Dict[str, str]:
        proxy_config = {
            "protocol": row["protocol"],
            "host": row["host"],
            "port": row["port"] or "8080",
            "url": row["url"],
        }
        if row["username"] and row["password"]:
            proxy_config["username"] = row["username"]
            proxy_config["password"] = row["password"]
        return proxy_config

    async def aget_proxy(self, site: Optional[str] = None) -> Optional[Dict[str, str]]:
        return await self.aget_proxy_by_protocol([], site=site)

    async def aget_proxy_by_protocol(
        self,
        supported_protocols: List[str],
        site: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        if not supported_protocols:
            logger.info("Selecting any protocol proxy")

        attempts = 0
        max_attempts = self._count_available(supported_protocols)
        if max_attempts == 0:
            logger.error("No available proxies for requested protocols")
            return None

        while attempts < max_attempts:
            attempts += 1
            with self._connect() as conn:
                row = self._select_candidate(conn, supported_protocols)
                if not row:
                    break

                proxy_url = row["url"]
                if not await self._test_proxy_async(proxy_url):
                    self._mark_proxy_error(proxy_url, "Proxy health-check failed", site=site, mark_failed=True)
                    logger.warning(f"Proxy {proxy_url} failed test, marked as failed")
                    continue

                if not self._try_lock_proxy(conn, row["id"], site=site):
                    continue

                logger.info(f"Assigned working proxy {proxy_url} ({self.get_available_count()} remaining unlocked)")
                return self._row_to_proxy_config(row)

        logger.error("No working proxies found for supported protocols")
        return None

    def get_proxy(self, site: Optional[str] = None) -> Optional[Dict[str, str]]:
        return self._run_async(self.aget_proxy(site=site))

    def get_proxy_by_protocol(
        self,
        supported_protocols: List[str],
        site: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        return self._run_async(self.aget_proxy_by_protocol(supported_protocols, site=site))

    def mark_proxy_success(self, proxy: Dict[str, str], site: Optional[str] = None) -> None:
        proxy_url = proxy.get("url") if proxy else None
        if not proxy_url:
            return
        self._mark_proxy_success(proxy_url, site=site)

    def mark_proxy_error(
        self,
        proxy: Dict[str, str],
        error_message: str,
        site: Optional[str] = None,
        mark_failed: bool = False,
    ) -> None:
        proxy_url = proxy.get("url") if proxy else None
        if not proxy_url:
            return
        self._mark_proxy_error(proxy_url, error_message=error_message, site=site, mark_failed=mark_failed)

    def mark_proxy_failed(
        self,
        proxy: Dict[str, str],
        error_message: str = "Proxy marked as failed",
        site: Optional[str] = None,
    ) -> None:
        self.mark_proxy_error(proxy, error_message=error_message, site=site, mark_failed=True)

    def release_proxy_lock(self, proxy: Dict[str, str]) -> None:
        proxy_url = proxy.get("url") if proxy else None
        if not proxy_url:
            return

        with self._connect() as conn:
            row = self._get_proxy_by_url(conn, proxy_url)
            if not row:
                return
            conn.execute(
                """
                UPDATE proxies
                SET locked_at = NULL,
                    locked_by = NULL,
                    updated_at = ?
                WHERE id = ?
                  AND locked_by = ?
                """,
                (self._now_iso(), row["id"], self.process_id),
            )

    async def aget_fallback_proxy(
        self,
        failed_proxy: Optional[Dict[str, str]] = None,
        site: Optional[str] = None,
        error_message: str = "Proxy fallback requested",
    ) -> Optional[Dict[str, str]]:
        if failed_proxy:
            self.mark_proxy_failed(failed_proxy, error_message=error_message, site=site)
        return await self.aget_proxy(site=site)

    async def aget_fallback_proxy_by_protocol(
        self,
        supported_protocols: List[str],
        failed_proxy: Optional[Dict[str, str]] = None,
        site: Optional[str] = None,
        error_message: str = "Proxy fallback requested",
    ) -> Optional[Dict[str, str]]:
        if failed_proxy:
            self.mark_proxy_failed(failed_proxy, error_message=error_message, site=site)
        return await self.aget_proxy_by_protocol(supported_protocols, site=site)

    def get_fallback_proxy(
        self,
        failed_proxy: Optional[Dict[str, str]] = None,
        site: Optional[str] = None,
        error_message: str = "Proxy fallback requested",
    ) -> Optional[Dict[str, str]]:
        return self._run_async(
            self.aget_fallback_proxy(
                failed_proxy=failed_proxy,
                site=site,
                error_message=error_message,
            )
        )

    def get_fallback_proxy_by_protocol(
        self,
        supported_protocols: List[str],
        failed_proxy: Optional[Dict[str, str]] = None,
        site: Optional[str] = None,
        error_message: str = "Proxy fallback requested",
    ) -> Optional[Dict[str, str]]:
        return self._run_async(
            self.aget_fallback_proxy_by_protocol(
                supported_protocols=supported_protocols,
                failed_proxy=failed_proxy,
                site=site,
                error_message=error_message,
            )
        )

    def has_available_proxies(self) -> bool:
        return self.get_available_count() > 0

    def get_available_count(self) -> int:
        return self._count_available()

    def get_failed_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM proxies WHERE is_failed = 1").fetchone()
            return int(row["cnt"]) if row else 0

    def validate_proxy_count(self, required_count: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM proxies").fetchone()
            total_proxies = int(row["cnt"]) if row else 0

        if total_proxies < required_count:
            logger.error(
                f"Not enough proxies available. Required: {required_count}, "
                f"Available: {total_proxies} (in {self.proxies_file})"
            )
            return False
        return True

    def validate_proxy_count_by_protocol(self, engines_with_protocols: List[Tuple[str, List[str]]]) -> bool:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT protocol, COUNT(*) AS cnt
                FROM proxies
                WHERE is_failed = 0
                GROUP BY protocol
                """
            ).fetchall()
            protocol_availability = {row["protocol"]: int(row["cnt"]) for row in rows}

        satisfied_engines: List[str] = []
        unsatisfied_engines: List[str] = []

        for engine_name, supported_protocols in engines_with_protocols:
            if not supported_protocols:
                satisfied_engines.append(f"{engine_name} (supports: any)")
                continue

            has_compatible_proxy = any(protocol_availability.get(protocol, 0) > 0 for protocol in supported_protocols)
            if has_compatible_proxy:
                satisfied_engines.append(f"{engine_name} (supports: {', '.join(supported_protocols)})")
            else:
                unsatisfied_engines.append(f"{engine_name} (supports: {', '.join(supported_protocols)})")

        if unsatisfied_engines:
            logger.error("The following engines don't have compatible proxies:")
            for engine in unsatisfied_engines:
                logger.error(f"\t{engine}")
            logger.info(f"Available proxy protocols: {protocol_availability}")
            return False

        logger.info("All engines have compatible proxies:")
        for engine in satisfied_engines:
            logger.info(f"  {engine}")
        logger.info(f"Available proxy protocols: {protocol_availability}")
        return True

    def reset_locks(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE proxies
                SET locked_at = NULL,
                    locked_by = NULL,
                    updated_at = ?
                """,
                (self._now_iso(),),
            )
        logger.info("Proxy locks reset")

    def cleanup_stale_locks(self) -> None:
        now = datetime.utcnow()
        stale_before = now - timedelta(seconds=max(1, self.lock_stale_s))
        unlocked = 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, locked_at, locked_by
                FROM proxies
                WHERE locked_by IS NOT NULL
                """
            ).fetchall()

            for row in rows:
                locked_at_raw = row["locked_at"]
                locked_by = row["locked_by"]
                is_stale = False

                if locked_at_raw:
                    try:
                        is_stale = datetime.fromisoformat(locked_at_raw) <= stale_before
                    except ValueError:
                        is_stale = True
                else:
                    is_stale = True

                is_dead_process = not self._is_process_alive(locked_by)
                if is_stale or is_dead_process:
                    conn.execute(
                        """
                        UPDATE proxies
                        SET locked_at = NULL,
                            locked_by = NULL,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (self._now_iso(), row["id"]),
                    )
                    unlocked += 1

        if unlocked:
            logger.info(f"Unlocked {unlocked} stale/dead proxy locks on startup")

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE proxies
                SET is_failed = 0,
                    locked_at = NULL,
                    locked_by = NULL,
                    updated_at = ?
                """,
                (self._now_iso(),),
            )
        logger.info("Proxy state reset: locks cleared and failed flags dropped")

    def get_stats(self) -> Dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_loaded,
                    SUM(CASE WHEN locked_by IS NULL AND is_failed = 0 THEN 1 ELSE 0 END) AS available,
                    SUM(CASE WHEN use_count > 0 THEN 1 ELSE 0 END) AS used,
                    SUM(CASE WHEN is_failed = 1 THEN 1 ELSE 0 END) AS failed
                FROM proxies
                """
            ).fetchone()

        return {
            "total_loaded": int(row["total_loaded"] or 0),
            "available": int(row["available"] or 0),
            "used": int(row["used"] or 0),
            "failed": int(row["failed"] or 0),
        }


async def handle_proxy_fallback(
    engine,
    target_name: str,
    original_error: Exception,
    retry_function: Callable,
    proxy_manager_instance=None,
) -> Tuple[Any, Optional[str]]:
    """
    Handle proxy fallback when a proxy-related error occurs.

    :param engine: The browser engine instance
    :param target_name: Name of the target being tested
    :param original_error: The original error that occurred
    :param retry_function: The async function to retry (should be a coroutine)
    :param proxy_manager_instance: ProxyManager instance
    :return: (result, error_message)
    """
    if proxy_manager_instance is None:
        proxy_manager_instance = proxy_manager

    logger.warning(f"Proxy-related error for {target_name}: {original_error}")

    current_proxy = getattr(engine, "proxy", None)
    if current_proxy:
        proxy_manager_instance.mark_proxy_error(
            current_proxy,
            error_message=str(original_error),
            site=target_name,
            mark_failed=True,
        )

    if not (current_proxy and proxy_manager_instance.has_available_proxies()):
        logger.error(f"Proxy fallback not available for {target_name}")
        return None, str(original_error)

    supported_protocols = getattr(engine, "supported_proxy_protocols", ["http", "https"])
    configured_proxy_retries = int(settings.proxy.max_retries)
    unlimited_proxy_retries = configured_proxy_retries == 0
    max_proxy_retries = max(1, configured_proxy_retries) if not unlimited_proxy_retries else None
    attempt_errors: List[str] = []
    attempt = 0
    while unlimited_proxy_retries or (max_proxy_retries is not None and attempt < max_proxy_retries):
        attempt += 1
        attempt_label = f"{attempt}/unlimited" if unlimited_proxy_retries else f"{attempt}/{max_proxy_retries}"
        fallback_proxy = await proxy_manager_instance.aget_fallback_proxy_by_protocol(
            supported_protocols,
            failed_proxy=None,
            site=target_name,
            error_message=str(original_error),
        )
        if not fallback_proxy:
            if unlimited_proxy_retries:
                logger.warning(
                    f"No compatible fallback proxy available for {target_name} "
                    f"(supports: {supported_protocols}) on attempt {attempt_label}; retrying in 2s"
                )
                await asyncio.sleep(2)
                continue

            logger.error(
                f"No compatible fallback proxy available for {target_name} "
                f"(supports: {supported_protocols}) on attempt {attempt_label}"
            )
            break

        logger.info(
            f"Retrying {target_name} with fallback {fallback_proxy['protocol']} "
            f"proxy {fallback_proxy.get('host')}:{fallback_proxy.get('port')} "
            f"(attempt {attempt_label})"
        )

        try:
            await engine.stop()
            engine.proxy = fallback_proxy
            await engine.start()

            result = await retry_with_backoff(
                retry_function,
                max_retries=max(1, int(settings.MAX_RETRIES)),
            )
            proxy_manager_instance.mark_proxy_success(fallback_proxy, site=target_name)
            logger.info(f"Fallback proxy successful for {target_name}")
            return result, None
        except Exception as fallback_error:
            error_text = str(fallback_error)
            attempt_errors.append(error_text)
            proxy_manager_instance.mark_proxy_error(
                fallback_proxy,
                error_message=error_text,
                site=target_name,
                mark_failed=True,
            )
            logger.error(
                f"Fallback proxy failed for {target_name} "
                f"(attempt {attempt_label}): {fallback_error}"
            )

    suffix = f", Fallbacks: {' | '.join(attempt_errors)}" if attempt_errors else ""
    return None, f"Original: {str(original_error)}{suffix}"


proxy_manager = ProxyManager()
