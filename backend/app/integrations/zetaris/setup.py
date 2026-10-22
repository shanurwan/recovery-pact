"""Register RecoveryPact's three business sources in a Zetaris tenant. Idempotent.

    python -m app.integrations.zetaris.setup

Expects the Zetaris driver to reach this stack's PostgreSQL as
``recovery-pact-postgres-1`` (scripts/zetaris-setup.sh puts both on the
``rp-bridge`` network) and the calendar CSV to be copied into the Zetaris
file root (the script does that too).
"""

from __future__ import annotations

import os
import sys

from app.config import get_settings
from app.integrations.zetaris.client import ZetarisError, get_zetaris_client

PG_HOST = os.environ.get("ZETARIS_PG_HOST", "recovery-pact-postgres-1")
CSV_PATH = os.environ.get(
    "ZETARIS_CSV_PATH", "/home/zetaris/customer-data/shared/recoverypact/change_calendar.csv"
)


def _datasource(name: str, db: str, description: str) -> list[str]:
    return [
        f'CREATE DATASOURCE {name} DESCRIBE BY "{description}" OPTIONS ('
        f'jdbcdriver "org.postgresql.Driver", '
        f'jdbcurl "jdbc:postgresql://{PG_HOST}:5432/{db}", '
        f'username "zetaris_reader", password "zetaris_reader", schema "public")',
        f"REGISTER DATASOURCE TABLES FROM {name}",
    ]


def statements() -> list[str]:
    s = get_settings()
    return [
        *_datasource(s.zetaris_continuity_ds, "continuity", "RecoveryPact business system of record"),
        *_datasource(s.zetaris_shop_ds, "checkout", "RecoveryPact checkout event stream"),
        f'CREATE LIGHTNING DATABASE {s.zetaris_calendar_db} DESCRIBE BY "Change-calendar export" OPTIONS ()',
        f"CREATE LIGHTNING FILESTORE TABLE change_calendar FROM {s.zetaris_calendar_db} FORMAT csv "
        f'OPTIONS (path "{CSV_PATH}", header "true")',
    ]


def main() -> int:
    s = get_settings()
    if not s.zetaris_url:
        print("ZETARIS_URL is not set; nothing to do.")
        return 1
    client = get_zetaris_client()
    for sql in statements():
        try:
            client.query(sql)
            print(f"ok      {sql[:90]}")
        except ZetarisError as exc:
            msg = str(exc).lower()
            if "already" in msg or "exist" in msg or "duplicate" in msg:
                print(f"exists  {sql[:90]}")
            else:
                print(f"FAILED  {sql[:90]}\n        {str(exc)[:300]}")
                return 2
    # Prove the federation end to end with the Continuity Guardian's own question.
    check = (
        f"SELECT c.change_id, w.application_name, w.owner_team FROM {s.zetaris_calendar_db}.change_calendar c "
        f"JOIN {s.zetaris_continuity_ds}.workload_registry w ON c.scope = w.job_name"
    )
    res = client.query(check)
    print(f"federated join CSV x PostgreSQL: {len(res.rows)} row(s) in {res.latency_ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
