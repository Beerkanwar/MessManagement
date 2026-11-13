# Operations runbook

This runbook records the operational rules that are policy rather than code.
It covers retention, the bounded Django admin, scheduled jobs and deployment
secrets for the Hostel Mess Management System.

## Data retention [SPEC DBDD §23]

**No application job deletes audit, billing, ledger or synchronization
history.** Retention is a college policy decision, not a scheduled task.

- The college sets the retention period for audit, billing, ledger and sync
  history in writing.
- Any purge is a **DBA action**, performed only after:
  1. the college has approved the retention period, and
  2. a verified backup exists and has been restored in a scratch environment.
- Purges are executed by the database administrator with an explicit,
  reviewed script. They are never exposed through a management command, cron
  entry or API endpoint.
- Audit rows remain append-only until a DBA purge. The application role holds
  `INSERT` and `SELECT` only; the Phase 2 trigger rejects `UPDATE` and
  `DELETE` independently.

## Audit immutability and database roles

The audit table is protected in three layers:

1. **Privileges** — migration `audit.0002_audit_role_privileges` revokes
   `UPDATE` and `DELETE` from the role that runs migrations. In production the
   migrations must run as a non-superuser owner so this restriction binds the
   application role.
2. **Trigger** — the Phase 2 insert-only trigger rejects `UPDATE` and `DELETE`
   even if privileges were granted again.
3. **Application** — `AuditLog` refuses updates/deletes at the ORM level and the
   admin registers it read-only.

> Local development uses the PostgreSQL superuser `mess_dev`. Superusers bypass
> privilege checks, so the privilege layer is only observable in tests that
> `SET ROLE` to a restricted role, and in production. Never ship production with
> a superuser application login [SPEC SDD §101].

## Bounded Django admin [ImplementationGuide Phase 13]

- Path: `DJANGO_ADMIN_PATH` (default `ops-admin`), mounted at `/<path>/`. It is
  deliberately not `/admin/`.
- The reverse proxy must restrict this path to the college network.
- Sign-in: only **ACTIVE Super Admin** accounts. Staff status is derived from
  the `SUPER_ADMIN` role; it is not entered or trusted as a separate flag.
- Sessions expire after `DJANGO_ADMIN_SESSION_SECONDS` (default 3600 seconds).
- Editable models: Hostel, Mess, FoodItem, ApplicationVersionPolicy. Every save
  writes a `MASTER_DATA_CHANGED` audit row with old and new values.
- Everything else is read-only. Passwords, token hashes, OTP hashes and
  `StudentSecret` ciphertext are never displayed.
- No model offers a delete action: records are deactivated or superseded so
  referenced rows never disappear [SPEC DBDD §17].
- The admin is a second sign-in path using the same accounts and password
  rules. It grants no authority beyond the role system; it is not a substitute
  for server-side authorization.

## Migration review checklist

Every migration to `main` is reviewed like application code. A reviewer signs
off only when all of the following hold:

1. **Generated, not hand-edited** — `python manage.py makemigrations --check
   --dry-run` is clean, and the file was produced by Django or is a documented
   hand-written `RunSQL` with both `sql` and `reverse_sql`.
2. **Reversible** — `tests/test_migrations.py::test_all_migrations_are_reversible`
   passes locally and in CI. A migration that cannot be reversed needs an
   explicit, reviewed exception describing the recovery procedure.
3. **No silent data loss** — dropping or retyping a column/table has a written
   backfill plan, and the old value is preserved or exported first.
4. **Lock impact understood** — tables above 100k rows use `CONCURRENTLY` index
   creation or a staged add/backfill/swap; no long `ALTER TABLE` runs in the
   request path.
5. **Constraints named** — every check, unique and exclusion constraint has an
   explicit `name` matching the `db_table`/`..._check` convention so rollback
   errors are diagnosable.
6. **Seeds are idempotent** — seed migrations use `get_or_create`/`update_or_create`
   and are safe to re-run on an existing database.
7. **Contract impact checked** — schema changes to `/api/v1` are additive only
   after `phase-13-contract`; CI runs `scripts/check_schema_contract.py` against
   the newest `phase-*` tag.
8. **Tested on a production-like snapshot** — forward and backward migration
   rehearsed against a recent backup, including timing, before the release.
9. **Runner role** — migrations run as the non-superuser database owner so the
   audit privilege revocation binds the application role.
10. **Rollback path documented** — the release notes name the target revision,
    the backup to restore if needed, and whether the rollback is online.

## Deployment secrets (environment only)

Real secrets are never `SystemSetting` rows [SPEC DBDD §12, SDD §102]. Keep
them in the deployment secret store / environment:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL` (database credentials)
- `JWT_SIGNING_KEY`
- `QR_SECRET_ENCRYPTION_KEY` (student secret encryption; rotation via
  `SECRET_ENCRYPTION_KEYS`)
- SMTP/OTP credentials

The configuration API lists these registry entries with `env_only: true` and
rejects attempts to persist them as settings.

## Scheduled jobs

Install `deployment/crontab` (normally as `/etc/cron.d/messmanagement`). All
times are IST. Each command acquires a PostgreSQL advisory lock, is idempotent
and exits non-zero on failure so monitoring can alert.

| Job | Schedule | Purpose |
| --- | --- | --- |
| `generate_meal_occurrences` | daily 01:00 | Fill occurrences to the horizon |
| `advance_pauses` | every 15 min | Activate and complete pauses |
| `open_billing_period` | 1st of month 00:30 | Open the previous month's period |
| `verify_balances` | daily 03:00 | Recompute and compare cached balances |
| `provision_missing_secrets` | on demand | Backfill student QR secrets |

Run a job twice at any time: the second run either exits on the advisory lock
or completes as a no-op.

## Cold start

From an empty database:

1. Provision PostgreSQL 16 and point `DATABASE_URL` at it.
2. Run `python manage.py migrate` (all migrations and seeds).
3. Create the first Super Admin account and its `SUPER_ADMIN` role.
4. Run `python manage.py provision_missing_secrets` if students already exist.
5. Start the application and confirm `GET /health/ready` is healthy.
