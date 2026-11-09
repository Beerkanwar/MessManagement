# Synchronization protocol (Phase 8)

Authoritative contract: ImplementationGuide Phase 8, SPEC SDD §67-68, DBDD §11.
All calls are authenticated HTTPS requests from a registered Manager device.

## Endpoint

`POST /api/v1/sync/upload` (alias: `POST /api/v1/upload`)

| Part | Fields |
| --- | --- |
| Request | `batch_id` (UUID, safe to replay), `device_id`, `client_version`, `last_server_version` (opaque integer cursor, `0` on first call), `page_token` (bootstrap paging), `trusted_time_metadata` (`anchor_server_time`, `elapsed_seconds`, `state`), `pending_transaction_count`, `transactions[]` |
| Transaction | `transaction_id` (UUID), `entity_type` (`MEAL_CONSUMPTION` or `EXTRA_TRANSACTION`), `client_created_at`, `payload` |
| Meal payload | `student_id`, `roll_number_snapshot`, `mess_id`, `meal_type`, `meal_date`, `transaction_timestamp`, `verification_method`, `verification_result`; client prices are diagnostic only |
| Extra payload | `student_id`, `hostel_id`, `mess_id`, `extra_item_id`, `quantity`, `transaction_timestamp`; client prices are diagnostic only |
| Response | `batch_id`, `server_time`, `authorization_state`, `offline_windows`, `transaction_results[]`, `student_changes[]`, `student_removals[]`, `configuration_changes`, `attendance_changes`, `resolved_results[]`, `new_sync_cursor`, `cursor_issued_at`, `has_more`, `next_page_token` |

Per-transaction results use `SYNCHRONIZED`, `IDEMPOTENT_SUCCESS`, `DUPLICATE`,
`REJECTED`, `CONFLICT` or `RETRYABLE_ERROR` with a `result_code`, message and
server `entity_id`.

## Example request

```json
{
  "batch_id": "1fd6b1b6-6cc1-4f88-b0b7-6b1f6f2f2d64",
  "device_id": "dev-manager-1",
  "client_version": "1.4.0",
  "last_server_version": 128,
  "page_token": null,
  "trusted_time_metadata": {
    "anchor_server_time": "2026-11-09T06:30:00Z",
    "elapsed_seconds": 120,
    "state": "VALID"
  },
  "pending_transaction_count": 1,
  "transactions": [
    {
      "transaction_id": "80e4b4a1-2c9f-4e1f-9f1c-77f2c1a1b0a0",
      "entity_type": "MEAL_CONSUMPTION",
      "client_created_at": "2026-11-09T06:28:11Z",
      "payload": {
        "student_id": 41,
        "roll_number_snapshot": "23108001",
        "mess_id": 2,
        "meal_type": "LUNCH",
        "meal_date": "2026-11-09",
        "transaction_timestamp": "2026-11-09T06:28:11Z",
        "verification_method": "QR_HMAC_SHA256",
        "verification_result": "SUCCESS"
      }
    }
  ]
}
```

## Example response (abridged)

```json
{
  "batch_id": "1fd6b1b6-6cc1-4f88-b0b7-6b1f6f2f2d64",
  "server_time": "2026-11-09T06:30:02Z",
  "authorization_state": "ACTIVE",
  "offline_windows": {"normal_hours": 24, "grace_hours": 24},
  "transaction_results": [
    {
      "transaction_id": "80e4b4a1-2c9f-4e1f-9f1c-77f2c1a1b0a0",
      "status": "SYNCHRONIZED",
      "result_code": "SYNCHRONIZED",
      "result_message": "Meal recorded successfully.",
      "entity_id": "9912"
    }
  ],
  "student_changes": [
    {
      "student_id": 41,
      "roll_number": "23108001",
      "display_name": "Student Name",
      "student_status": "ACTIVE",
      "hostel_id": 3,
      "mess_id": 2,
      "assignment_version": 4,
      "change_version": 130,
      "pause_state": "NONE",
      "secret_version": 2,
      "secret_ciphertext": "..."
    }
  ],
  "student_removals": [{"student_id": 17, "reason": "ASSIGNMENT_ENDED"}],
  "configuration_changes": {"mess": {}, "meal_rate": "48.0000", "extra_items": [], "meal_occurrences": [], "system_settings": {}},
  "attendance_changes": {"meals": [], "extras": []},
  "resolved_results": [
    {
      "transaction_id": "3124a2c8-dca1-4a8e-9ba3-76f2a0cda1e6",
      "status": "SYNCHRONIZED",
      "conflict_type": "ASSIGNMENT_CHANGED",
      "resolution": "ACCEPTED",
      "resolution_notes": "Assignment record was late",
      "resolved_at": "2026-11-09T06:05:00Z",
      "entity_id": "9910"
    }
  ],
  "new_sync_cursor": 131,
  "cursor_issued_at": "2026-11-09T06:30:02Z",
  "has_more": false,
  "next_page_token": null
}
```

## Client state mapping [App Flow §8]

| Server result | Local state |
| --- | --- |
| `SYNCHRONIZED`, `IDEMPOTENT_SUCCESS`, `DUPLICATE` | `SYNCHRONIZED` |
| `REJECTED` | `REJECTED`, reason visible |
| `CONFLICT` | `CONFLICT`, reason visible until resolved |
| `RETRYABLE_ERROR` | back to `PENDING` with backoff |

## Idempotency and paging

- Replaying a `batch_id` that already completed returns the stored per-item
  results plus a fresh download. Replaying a `transaction_id` returns its
  original result.
- A first call (`last_server_version: 0`) is a full bootstrap. Follow
  `next_page_token` until `has_more` is false. Each page returns unique
  students; the union is the authorized roster.
- Downloads carry only students with an ACTIVE assignment to the Manager's
  mess, their `LocalStudent` fields, and extras for those hostels.

## Conflict resolution [DEC-17]

`GET /api/v1/sync/conflicts`, `GET /api/v1/sync/conflicts/{id}` and
`POST /api/v1/sync/conflicts/{id}/resolve` are Super Admin endpoints.

```json
{"resolution": "ACCEPTED", "notes": "Assignment record was late"}
```

`ACCEPTED` re-runs the original command with only the conflicting check waived
(`ASSIGNMENT_CHANGED`, `MEAL_CANCELLED` or `UNAUTHORIZED_SCOPE`) and Source
`SYNC_RESOLUTION`. Uniqueness and locked billing periods are never waived:
accepting a `LOCKED_PERIOD_EXTRA` returns `LOCKED_PERIOD_NOT_WAIVABLE`.
`REJECTED` closes the conflict. Both require notes and write audit.

## Test tool

`backend/scripts/fake_manager_client.py` bootstraps, uploads one meal and
downloads again using only the Python standard library.
