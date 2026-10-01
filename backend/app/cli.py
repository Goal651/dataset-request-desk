"""CLI: import episodes from a CSV file (the other half of the import story).

    python -m app.cli import /seed/episodes.csv

Prints the same structured report as the HTTP endpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="drd")
    sub = parser.add_subparsers(dest="command", required=True)

    import_parser = sub.add_parser("import", help="Import episodes from a CSV export")
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument(
        "--json", action="store_true", help="Print the full per-row report as JSON"
    )

    args = parser.parse_args()

    if args.command == "import":
        from app.db import SessionLocal
        from app.routers.episodes import import_csv_bytes

        content = args.csv_path.read_bytes()
        session = SessionLocal()
        try:
            report = import_csv_bytes(content, session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        print(
            f"rows_seen={report.rows_seen} imported={report.imported} "
            f"updated={report.updated} skipped={report.skipped}"
        )
        if args.json:
            from dataclasses import asdict

            print(
                json.dumps(
                    {
                        "rows_seen": report.rows_seen,
                        "imported": report.imported,
                        "updated": report.updated,
                        "skipped": report.skipped,
                        "rows": [asdict(r) for r in report.rows],
                    },
                    indent=2,
                )
            )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
