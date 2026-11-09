"""
Fake Manager client for the Phase 8 synchronization protocol.

This is a test tool, not part of the mobile app. It exercises the same three
operations a Manager performs:

1. Bootstrap download with an empty cursor.
2. Upload a batch containing one meal transaction.
3. Download again with the new cursor.

Usage (from the repository root, with the backend running):

    python backend/scripts/fake_manager_client.py \
        --base-url http://127.0.0.1:8000 \
        --token "$MANAGER_TOKEN" \
        --device-id dev-manager-1 \
        --student-id 1 \
        --mess-id 1 \
        --meal-type LUNCH \
        --meal-date 2026-11-09

The token must belong to an active MESS_MANAGER device. Only the standard
library is used so the script runs without installing anything.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import urllib.error
import urllib.request
import uuid


def call(base_url: str, token: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/sync/upload",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"sync upload failed with HTTP {exc.code}: {detail}") from exc


def bootstrap(args) -> dict:
    return download(args, 0)


def upload_meal(args, student_id: int, mess_id: int, meal_date: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    transaction_id = str(uuid.uuid4())
    response = call(
        args.base_url,
        args.token,
        {
            "batch_id": str(uuid.uuid4()),
            "device_id": args.device_id,
            "last_server_version": 0,
            "trusted_time_metadata": {
                "anchor_server_time": now,
                "elapsed_seconds": 0,
                "state": "VALID",
            },
            "pending_transaction_count": 0,
            "transactions": [
                {
                    "transaction_id": transaction_id,
                    "entity_type": "MEAL_CONSUMPTION",
                    "client_created_at": now,
                    "payload": {
                        "student_id": student_id,
                        "mess_id": mess_id,
                        "meal_type": args.meal_type,
                        "meal_date": meal_date,
                        "transaction_timestamp": now,
                        "verification_method": "QR_HMAC_SHA256",
                        "verification_result": "SUCCESS",
                    },
                }
            ],
        },
    )
    result = response["transaction_results"][0]
    print(f"upload transaction {transaction_id}: {result['status']} {result['result_code']}")
    return response


def download(args, cursor: int) -> dict:
    """Download all pages and return the final page (which carries the cursor)."""
    page_token = None
    response: dict = {}
    while True:
        body = {
            "device_id": args.device_id,
            "last_server_version": cursor,
            "transactions": [],
        }
        if page_token is not None:
            body["page_token"] = page_token
        response = call(args.base_url, args.token, body)
        print(
            f"download: {len(response['student_changes'])} student upsert(s), "
            f"{len(response.get('student_removals', []))} removal(s), "
            f"{len(response.get('resolved_results', []))} resolved result(s), "
            f"new cursor {response['new_sync_cursor']}, has_more={response['has_more']}"
        )
        if not response["has_more"]:
            return response
        page_token = response["next_page_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="Manager access token")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--mess-id", type=int, required=True)
    parser.add_argument("--meal-type", default="LUNCH")
    parser.add_argument(
        "--meal-date",
        required=True,
        help="IST calendar date, YYYY-MM-DD",
    )
    args = parser.parse_args()

    first = bootstrap(args)
    upload = upload_meal(args, args.student_id, args.mess_id, args.meal_date)
    after = download(args, upload["new_sync_cursor"])
    if after["new_sync_cursor"] < first["new_sync_cursor"]:
        print("warning: cursor moved backwards", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
