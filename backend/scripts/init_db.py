#!/usr/bin/env python3
"""Create tables and sync the clothing catalog. Idempotent.

Usage:  python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.services import catalog  # noqa: E402


def main() -> int:
    settings.ensure_dirs()
    init_db()
    print(f"database ready: {settings.database_url}")
    with SessionLocal() as db:
        report = catalog.sync_catalog(db)
    print(
        f"catalog: +{len(report['added'])} added, "
        f"~{len(report['updated'])} updated, "
        f"-{len(report['deactivated'])} deactivated, "
        f"{report['total_active']} active"
    )
    for slug in report["added"]:
        print(f"  + {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
