#!/usr/bin/env python3
import argparse
from pathlib import Path
from urllib.parse import urlparse


PAIR_RULES = {
    5501: [("socks5", 5501), ("http", 5000)],
    5000: [("socks5", 5501), ("http", 5000)],
    8085: [("http", 8085), ("socks5", 1085)],
    1085: [("http", 8085), ("socks5", 1085)],
}


def parse_proxy(raw_line: str):
    raw = raw_line.strip()
    if not raw or raw.startswith("#"):
        return None

    normalized = raw if "://" in raw else f"http://{raw}"
    parsed = urlparse(normalized)
    if not parsed.hostname or not parsed.port:
        return None

    scheme = (parsed.scheme or "http").lower()
    if scheme == "socks5h":
        scheme = "socks5"

    return {
        "scheme": scheme,
        "host": parsed.hostname,
        "port": int(parsed.port),
        "username": parsed.username,
        "password": parsed.password,
    }


def format_proxy(scheme: str, host: str, port: int, username: str | None, password: str | None) -> str:
    if username and password:
        return f"{scheme}://{username}:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def expand_proxy(entry: dict) -> list[str]:
    pair = PAIR_RULES.get(entry["port"])
    if not pair:
        return [
            format_proxy(
                entry["scheme"],
                entry["host"],
                entry["port"],
                entry["username"],
                entry["password"],
            )
        ]

    return [
        format_proxy(scheme, entry["host"], port, entry["username"], entry["password"])
        for scheme, port in pair
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Expand proxy list into protocol pairs by port mapping."
    )
    parser.add_argument(
        "--input",
        default="documents/proxies.txt",
        help="Input proxies file (default: documents/proxies.txt)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file (default: overwrite input)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create .bak copy before overwrite",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    lines = input_path.read_text(encoding="utf-8").splitlines()

    output = []
    seen = set()
    for line in lines:
        parsed = parse_proxy(line)
        if not parsed:
            continue
        for proxy in expand_proxy(parsed):
            if proxy in seen:
                continue
            seen.add(proxy)
            output.append(proxy)

    if args.backup and output_path == input_path:
        backup_path = input_path.with_suffix(input_path.suffix + ".bak")
        backup_path.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")

    print(f"Input lines: {len(lines)}")
    print(f"Output proxies: {len(output)}")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
