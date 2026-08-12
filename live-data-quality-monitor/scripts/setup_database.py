"""Create the MySQL schema used to store validation history."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.database import ensure_schema


def main() -> int:
    """Create the MySQL database and validation tables if needed."""

    try:
        ensure_schema()
    except RuntimeError as exc:
        print(f"Database setup failed: {exc}")
        return 1

    print("Database tables created successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

