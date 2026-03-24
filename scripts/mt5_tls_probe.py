import argparse
import asyncio
import json
import ssl
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings


@dataclass
class ProbeResult:
    timestamp: str
    label: str
    ok: bool
    status_code: int | None
    error_type: str | None
    error_message: str | None


def build_ssl_context(label: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if label == "tls12":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    elif label == "tls13":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    elif label == "default":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    else:
        raise ValueError(f"Unsupported label: {label}")

    return ctx


async def probe_once(base_url: str, params: dict[str, str], label: str) -> ProbeResult:
    ctx = build_ssl_context(label)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            verify=ctx,
            timeout=httpx.Timeout(10.0, connect=10.0),
            trust_env=False,
        ) as client:
            resp = await client.get("/api/auth/start", params=params)
            return ProbeResult(
                timestamp=timestamp,
                label=label,
                ok=resp.status_code == 200,
                status_code=resp.status_code,
                error_type=None,
                error_message=None if resp.status_code == 200 else resp.text[:200],
            )
    except Exception as exc:
        return ProbeResult(
            timestamp=timestamp,
            label=label,
            ok=False,
            status_code=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe MT5 auth/start with different TLS versions.")
    parser.add_argument("--interval", type=int, default=5, help="Probe interval in seconds.")
    parser.add_argument("--rounds", type=int, default=60, help="How many rounds to run.")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["tls12", "tls13"],
        choices=["tls12", "tls13", "default"],
        help="TLS modes to test in parallel.",
    )
    parser.add_argument(
        "--output",
        default="share/mt5_tls_probe_results.jsonl",
        help="Output JSONL file path.",
    )
    args = parser.parse_args()

    settings = get_settings()
    base_url = f"https://{settings.MT5_SERVER_HOST}:{settings.MT5_SERVER_PORT}"
    params = {
        "version": "3470",
        "agent": "AstralWGateway",
        "login": str(settings.MT5_MANAGER_LOGIN),
        "type": "manager",
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    counters: dict[str, Counter] = {mode: Counter() for mode in args.modes}

    print(f"target={base_url}/api/auth/start")
    print(f"modes={','.join(args.modes)} interval={args.interval}s rounds={args.rounds}")
    print(f"output={output_path}")

    with output_path.open("a", encoding="utf-8") as fh:
        for round_idx in range(1, args.rounds + 1):
            results = await asyncio.gather(*(probe_once(base_url, params, mode) for mode in args.modes))
            print(f"\n[{round_idx}/{args.rounds}]")
            for result in results:
                if result.ok:
                    counters[result.label]["ok"] += 1
                    print(f"{result.timestamp} {result.label:<7} OK   status={result.status_code}")
                else:
                    key = result.error_type or f"HTTP_{result.status_code}"
                    counters[result.label][key] += 1
                    print(
                        f"{result.timestamp} {result.label:<7} FAIL "
                        f"type={result.error_type or 'HTTP'} msg={result.error_message}"
                    )
                fh.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")
                fh.flush()

            if round_idx < args.rounds:
                await asyncio.sleep(args.interval)

    print("\nSummary")
    for mode in args.modes:
        print(f"{mode}: {dict(counters[mode])}")


if __name__ == "__main__":
    asyncio.run(main())
