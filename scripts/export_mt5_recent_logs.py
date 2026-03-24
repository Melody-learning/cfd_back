import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.mt5.auth import compute_srv_rand_answer, generate_cli_rand, verify_cli_rand_answer


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export recent MT5 server logs.")
    parser.add_argument("--from", dest="from_ts", required=True, help="Unix timestamp, inclusive.")
    parser.add_argument("--to", dest="to_ts", required=True, help="Unix timestamp, inclusive.")
    parser.add_argument(
        "--output",
        default="share/mt5_recent_logs.jsonl",
        help="Output JSONL file path.",
    )
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=["Time", "Network", "WebAPI", "disconnect", "timeout", "limit", "flood", "session"],
        help="Only keep logs containing one of these keywords in source/message.",
    )
    args = parser.parse_args()

    settings = get_settings()
    base_url = f"https://{settings.MT5_SERVER_HOST}:{settings.MT5_SERVER_PORT}"
    password = settings.MT5_WEBAPI_PASSWORD or settings.MT5_MANAGER_PASSWORD

    async with httpx.AsyncClient(
        base_url=base_url,
        verify=settings.MT5_USE_SSL_VERIFY,
        timeout=httpx.Timeout(60.0, connect=10.0),
        trust_env=False,
    ) as client:
        start_data = (
            await client.get(
                "/api/auth/start",
                params={
                    "version": "3470",
                    "agent": "AstralWGateway",
                    "login": str(settings.MT5_MANAGER_LOGIN),
                    "type": "manager",
                },
            )
        ).json()
        srv_rand_answer = compute_srv_rand_answer(password, start_data["srv_rand"])
        cli_rand_bytes, cli_rand_hex = generate_cli_rand()
        answer_data = (
            await client.get(
                "/api/auth/answer",
                params={"srv_rand_answer": srv_rand_answer, "cli_rand": cli_rand_hex},
            )
        ).json()
        if not verify_cli_rand_answer(password, cli_rand_bytes, answer_data.get("cli_rand_answer", "")):
            raise RuntimeError("MT5 auth verify failed")

        response = await client.get(
            "/api/logger/server_request",
            params={"mode": "2", "type": "0", "from": args.from_ts, "to": args.to_ts},
        )
        data = response.json()
        logs = data.get("answer", [])

    keywords = [k.lower() for k in args.keywords]
    filtered = []
    for item in logs:
        blob = f"{item.get('source', '')} {item.get('message', '')}".lower()
        if any(k.lower() in blob for k in keywords):
            filtered.append(item)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for item in filtered:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"exported={len(filtered)}")
    print(f"output={output_path}")
    print(f"from={args.from_ts} to={args.to_ts}")
    print(f"generated_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
