"""MySQL persistence helpers for validation runs and issue history."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

Issue = dict[str, Any]
_SCHEMA_READY = False


def _load_dotenv() -> None:
    """Load environment variables from the project .env file."""

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is required. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    load_dotenv(ENV_PATH)


def _load_secret_values() -> dict[str, str]:
    """Read MySQL settings from Streamlit secrets when available."""

    try:
        import streamlit as st  # type: ignore
    except ImportError:
        return {}

    try:
        secrets = st.secrets
    except Exception:
        return {}

    values: dict[str, str] = {}
    direct_keys = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "MYSQL_PORT")
    for key in direct_keys:
        try:
            value = secrets[key]
        except Exception:
            value = None
        if value:
            values[key] = str(value).strip()

    try:
        mysql_block = secrets.get("mysql", {})
    except Exception:
        mysql_block = {}

    if isinstance(mysql_block, dict):
        mapping = {
            "MYSQL_HOST": ("host", "mysql_host"),
            "MYSQL_USER": ("user", "mysql_user"),
            "MYSQL_PASSWORD": ("password", "mysql_password"),
            "MYSQL_DATABASE": ("database", "mysql_database"),
            "MYSQL_PORT": ("port", "mysql_port"),
        }
        for env_key, candidates in mapping.items():
            if env_key in values:
                continue
            for candidate in candidates:
                if candidate in mysql_block and mysql_block[candidate]:
                    values[env_key] = str(mysql_block[candidate]).strip()
                    break

    return values


def _get_mysql_connector():
    """Import mysql.connector lazily so the module stays importable offline."""

    try:
        import mysql.connector as mysql_connector
    except ImportError as exc:
        raise RuntimeError(
            "mysql-connector-python is required. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    return mysql_connector


def _load_db_config(include_database: bool = True) -> dict[str, Any]:
    """Read MySQL connection settings from environment variables."""

    _load_dotenv()

    host = os.getenv("MYSQL_HOST", "").strip()
    user = os.getenv("MYSQL_USER", "").strip()
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DATABASE", "").strip()
    port_text = os.getenv("MYSQL_PORT", "3306").strip()

    secret_values = _load_secret_values()
    if secret_values:
        host = secret_values.get("MYSQL_HOST", host)
        user = secret_values.get("MYSQL_USER", user)
        password = secret_values.get("MYSQL_PASSWORD", password)
        database = secret_values.get("MYSQL_DATABASE", database)
        port_text = secret_values.get("MYSQL_PORT", port_text)

    missing = [
        name
        for name, value in (
            ("MYSQL_HOST", host),
            ("MYSQL_USER", user),
            ("MYSQL_PASSWORD", password),
            ("MYSQL_DATABASE", database),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing MySQL configuration in .env: " + ", ".join(missing)
        )

    try:
        port = int(port_text)
    except ValueError as exc:
        raise RuntimeError("MYSQL_PORT must be an integer value.") from exc

    config: dict[str, Any] = {
        "host": host,
        "user": user,
        "password": password,
        "port": port,
        "connection_timeout": 10,
    }

    if host not in {"localhost", "127.0.0.1", "::1"}:
        config["ssl_disabled"] = False

    if include_database:
        config["database"] = database

    return config


def is_mysql_configured() -> bool:
    """Return True when the MySQL connection settings are available."""

    try:
        _load_db_config(include_database=True)
    except RuntimeError:
        return False
    return True


def _connect(include_database: bool = True):
    """Open a MySQL connection using the loaded environment settings."""

    mysql_connector = _get_mysql_connector()
    config = _load_db_config(include_database=include_database)

    try:
        return mysql_connector.connect(**config)
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        db_name = config.get("database", "(server)")
        raise RuntimeError(
            f"Could not connect to MySQL {db_name!r} at "
            f"{config['host']}:{config['port']}. "
            "Make sure the server is reachable, the credentials are correct, and "
            "SSL/TLS is allowed by the MySQL service if you are using a hosted database."
        ) from exc


def _create_validation_tables(cursor) -> None:
    """Create the validation history tables on an existing database connection."""

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id INT AUTO_INCREMENT PRIMARY KEY,
            run_timestamp DATETIME NOT NULL,
            total_rows INT NOT NULL,
            completeness FLOAT NOT NULL,
            validity FLOAT NOT NULL,
            uniqueness FLOAT NOT NULL,
            consistency FLOAT NOT NULL,
            overall_score FLOAT NOT NULL,
            status VARCHAR(20) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            issue_id INT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            column_name VARCHAR(255) NOT NULL,
            issue_type VARCHAR(100) NOT NULL,
            issue_count INT NOT NULL,
            severity VARCHAR(20) NOT NULL,
            details TEXT,
            CONSTRAINT fk_issues_runs
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def ensure_schema() -> None:
    """Create the database and tables if they do not already exist."""

    mysql_connector = _get_mysql_connector()
    db_config = _load_db_config(include_database=False)
    database_name = os.getenv("MYSQL_DATABASE", "").strip()

    if not database_name:
        raise RuntimeError("MYSQL_DATABASE is missing from .env.")

    connection = None
    cursor = None

    try:
        connection = mysql_connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        connection.commit()
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError(
            "Failed to create or access the MySQL database. "
            "Check that the server is running and the credentials in .env are valid."
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    connection = None
    cursor = None
    try:
        connection = _connect(include_database=True)
        cursor = connection.cursor()
        _create_validation_tables(cursor)

        connection.commit()
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError(
            "Failed to create validation tables in MySQL."
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def _ensure_schema_ready() -> None:
    """Create the schema once per process before the first write/read."""

    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    mysql_connector = _get_mysql_connector()
    connection = _connect(include_database=True)
    cursor = None

    try:
        cursor = connection.cursor()
        _create_validation_tables(cursor)
        connection.commit()
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError(
            "Failed to prepare validation tables in MySQL."
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()

    _SCHEMA_READY = True


def save_run_results(score_result: dict[str, Any], total_rows: int) -> int:
    """Insert a validation run and return the new run_id."""

    _ensure_schema_ready()
    mysql_connector = _get_mysql_connector()
    connection = _connect(include_database=True)
    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO runs (
                run_timestamp,
                total_rows,
                completeness,
                validity,
                uniqueness,
                consistency,
                overall_score,
                status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                datetime.now(timezone.utc).replace(tzinfo=None),
                int(total_rows),
                float(score_result["completeness"]),
                float(score_result["validity"]),
                float(score_result["uniqueness"]),
                float(score_result["consistency"]),
                float(score_result["overall_score"]),
                str(score_result["status"]),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError("Failed to save the validation run to MySQL.") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


def save_issues(run_id: int, issues: list[Issue]) -> int:
    """Insert one row per issue for the given run and return the row count."""

    if not issues:
        return 0

    _ensure_schema_ready()
    mysql_connector = _get_mysql_connector()
    connection = _connect(include_database=True)
    cursor = None

    rows = [
        (
            int(run_id),
            str(issue.get("column", "")),
            str(issue.get("issue_type", "")),
            int(issue.get("count", 0)),
            str(issue.get("severity", "")),
            str(issue.get("details", "")),
        )
        for issue in issues
    ]

    try:
        cursor = connection.cursor()
        cursor.executemany(
            """
            INSERT INTO issues (
                run_id,
                column_name,
                issue_type,
                issue_count,
                severity,
                details
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        connection.commit()
        return cursor.rowcount
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError("Failed to save validation issues to MySQL.") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


def get_recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent validation runs as dictionaries."""

    try:
        limit_value = max(1, int(limit))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer value.") from exc

    _ensure_schema_ready()
    mysql_connector = _get_mysql_connector()
    connection = _connect(include_database=True)
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT run_id, run_timestamp, total_rows, overall_score, status
            FROM runs
            ORDER BY run_timestamp DESC
            LIMIT %s
            """,
            (limit_value,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except mysql_connector.Error as exc:  # type: ignore[attr-defined]
        raise RuntimeError("Failed to load recent validation runs from MySQL.") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()
