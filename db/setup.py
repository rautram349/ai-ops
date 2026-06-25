"""Database setup script for E-commerce Operations Brain.

Responsibilities:
    1. Connect to the PostgreSQL server using the admin (postgres) credentials
       from the environment.
    2. Create the application database if it does not already exist.
    3. Run every *.sql migration file found in db/migrations/ in ascending
       filename order (i.e. 001_…, 002_…, …).
    4. Track which migrations have already been applied in a
       ``schema_migrations`` bookkeeping table so the script is safe to re-run.

Usage::

    python -m db.setup                  # run from the project root
    python -m db.setup --reset          # DROP and re-create the database first
    python -m db.setup --dry-run        # print SQL without executing

Environment variables (via .env or shell)::

    DATABASE_URL_SYNC   Full psycopg2 DSN, e.g.
                        postgresql://postgres:postgres@localhost:5432/ecommerce_ops_brain
                        The database name is extracted from this URL.
                        A server-level connection (without the database part) is
                        used for the CREATE DATABASE step.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BOOKKEEPING_TABLE = "schema_migrations"

# ---------------------------------------------------------------------------
# DSN helpers
# ---------------------------------------------------------------------------


def _parse_dsn(database_url: str) -> dict:
    """Parse a psycopg2-compatible DSN string into a keyword-argument dict.

    Args:
        database_url: Full DSN, e.g.
            ``postgresql://user:pass@host:5432/dbname``.

    Returns:
        Dict with keys accepted by ``psycopg2.connect`` (host, port, user,
        password, dbname).

    Raises:
        ValueError: If the DSN cannot be parsed.
    """
    try:
        from urllib.parse import unquote, urlparse
        parsed = urlparse(database_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": unquote(parsed.username) if parsed.username else "postgres",
            "password": unquote(parsed.password) if parsed.password else "",
            "dbname": parsed.path.lstrip("/") if parsed.path else "postgres",
        }
    except Exception as exc:
        raise ValueError(f"Could not parse DATABASE_URL_SYNC: {exc}") from exc


def _server_dsn(params: dict) -> dict:
    """Return a copy of *params* connected to the ``postgres`` maintenance DB.

    This connection is used for server-level operations such as
    CREATE DATABASE or DROP DATABASE, which cannot be run inside a
    regular database connection to the target DB.

    Args:
        params: Dict returned by :func:`_parse_dsn`.

    Returns:
        New dict identical to *params* but with ``dbname`` set to
        ``"postgres"``.
    """
    server_params = dict(params)
    server_params["dbname"] = "postgres"
    return server_params


# ---------------------------------------------------------------------------
# Database-level operations
# ---------------------------------------------------------------------------


def database_exists(server_conn, dbname: str) -> bool:
    """Check whether a PostgreSQL database already exists.

    Args:
        server_conn: An open psycopg2 connection to the ``postgres`` DB.
        dbname: Name of the database to check.

    Returns:
        True if the database exists, False otherwise.
    """
    with server_conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,),
        )
        return cur.fetchone() is not None


def create_database(server_conn, dbname: str) -> None:
    """Create a new PostgreSQL database.

    Args:
        server_conn: An open psycopg2 connection to the ``postgres`` DB.
            Must be in AUTOCOMMIT mode (CREATE DATABASE cannot run inside a
            transaction).
        dbname: Name of the database to create.

    Raises:
        psycopg2.Error: If the CREATE DATABASE statement fails.
    """
    logger.info("Creating database '%s'", dbname)
    with server_conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname))
        )
    logger.info("Database '%s' created successfully", dbname)


def drop_database(server_conn, dbname: str) -> None:
    """Drop an existing PostgreSQL database (used with --reset).

    Terminates all active connections to the database before dropping it
    so the DROP statement does not block.

    Args:
        server_conn: An open psycopg2 connection to the ``postgres`` DB.
            Must be in AUTOCOMMIT mode.
        dbname: Name of the database to drop.

    Raises:
        psycopg2.Error: If the DROP DATABASE statement fails.
    """
    logger.warning("Terminating all connections to '%s'", dbname)
    with server_conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM   pg_stat_activity
            WHERE  datname = %s
              AND  pid <> pg_backend_pid()
            """,
            (dbname,),
        )

    logger.warning("Dropping database '%s'", dbname)
    with server_conn.cursor() as cur:
        cur.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
        )
    logger.info("Database '%s' dropped", dbname)


# ---------------------------------------------------------------------------
# Migration bookkeeping
# ---------------------------------------------------------------------------


def ensure_bookkeeping_table(conn) -> None:
    """Create the schema_migrations tracking table if it does not exist.

    This table records which migration files have already been applied.
    It is always created before any migrations are run.

    Args:
        conn: An open psycopg2 connection to the application database.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {BOOKKEEPING_TABLE} (
                filename    VARCHAR(255) PRIMARY KEY,
                applied_at  TIMESTAMP    NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()
    logger.debug("Bookkeeping table '%s' is ready", BOOKKEEPING_TABLE)


def applied_migrations(conn) -> set[str]:
    """Return the set of migration filenames already recorded as applied.

    Args:
        conn: An open psycopg2 connection to the application database.

    Returns:
        Set of filenames (e.g. ``{"001_initial_schema.sql"}``).
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {BOOKKEEPING_TABLE}")
        return {row[0] for row in cur.fetchall()}


def record_migration(conn, filename: str) -> None:
    """Insert a migration filename into the bookkeeping table.

    Args:
        conn: An open psycopg2 connection to the application database.
        filename: The migration filename that was just applied.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {BOOKKEEPING_TABLE} (filename) VALUES (%s)",
            (filename,),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def collect_migrations() -> list[Path]:
    """Discover and sort migration SQL files in the migrations directory.

    Files are sorted lexicographically (ascending), so the numeric prefix
    (001_, 002_, …) determines execution order.

    Returns:
        Sorted list of ``Path`` objects pointing to ``*.sql`` files.

    Raises:
        FileNotFoundError: If the migrations directory does not exist.
    """
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(
            f"Migrations directory not found: {MIGRATIONS_DIR}"
        )
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    logger.debug("Found %d migration file(s) in %s", len(files), MIGRATIONS_DIR)
    return files


def run_migrations(conn, dry_run: bool = False) -> None:
    """Apply all pending migration files to the database.

    Reads each ``*.sql`` file from the migrations directory in order.
    Skips files already recorded in the bookkeeping table.
    Each migration is executed inside its own transaction; if a migration
    fails, the transaction is rolled back and an error is raised so that
    subsequent migrations are not attempted.

    Args:
        conn: An open psycopg2 connection to the application database.
        dry_run: If True, print each migration's SQL without executing it.

    Raises:
        psycopg2.Error: If any migration fails.
        FileNotFoundError: If the migrations directory does not exist.
    """
    ensure_bookkeeping_table(conn)
    already_applied = applied_migrations(conn)

    migration_files = collect_migrations()
    pending = [f for f in migration_files if f.name not in already_applied]

    if not pending:
        logger.info("All %d migration(s) already applied — nothing to do", len(migration_files))
        return

    logger.info(
        "%d pending migration(s) out of %d total",
        len(pending),
        len(migration_files),
    )

    for migration_file in pending:
        sql_text = migration_file.read_text(encoding="utf-8")

        if dry_run:
            print(f"\n-- DRY RUN: {migration_file.name} --")
            print(sql_text)
            continue

        logger.info("Applying migration: %s", migration_file.name)
        try:
            with conn.cursor() as cur:
                cur.execute(sql_text)
            record_migration(conn, migration_file.name)
            logger.info("Migration applied successfully: %s", migration_file.name)
        except psycopg2.Error as exc:
            conn.rollback()
            logger.error(
                "Migration '%s' failed — transaction rolled back. Error: %s",
                migration_file.name,
                exc,
            )
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed namespace with attributes: reset (bool), dry_run (bool).
    """
    parser = argparse.ArgumentParser(
        description="Set up the E-commerce Operations Brain database and run migrations."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DROP and re-create the database before running migrations. "
             "WARNING: destroys all existing data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print migration SQL without executing it.",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the database setup script.

    Loads environment variables, resolves the target database name,
    creates the database if needed, and runs all pending migrations.

    Raises:
        SystemExit: With exit code 1 on any unrecoverable error.
    """
    load_dotenv()
    args = _parse_args()

    database_url = os.getenv("DATABASE_URL_SYNC")
    if not database_url:
        logger.critical(
            "DATABASE_URL_SYNC is not set. "
            "Copy .env.example to .env and fill in the value."
        )
        sys.exit(1)

    try:
        params = _parse_dsn(database_url)
    except ValueError as exc:
        logger.critical("Invalid DATABASE_URL_SYNC: %s", exc)
        sys.exit(1)

    dbname = params.get("dbname") or params.get("database")
    if not dbname:
        logger.critical("Could not determine database name from DATABASE_URL_SYNC")
        sys.exit(1)

    server_params = _server_dsn(params)

    # ------------------------------------------------------------------
    # Step 1: server-level connection (CREATE / DROP DATABASE)
    # ------------------------------------------------------------------
    logger.info("Connecting to PostgreSQL server at %s:%s", params.get("host", "localhost"), params.get("port", 5432))
    try:
        server_conn = psycopg2.connect(**server_params)
        server_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    except psycopg2.OperationalError as exc:
        logger.critical(
            "Cannot connect to PostgreSQL server. "
            "Is the server running? Error: %s",
            exc,
        )
        sys.exit(1)

    try:
        # --reset: drop the DB so the next block re-creates it cleanly
        if args.reset:
            if database_exists(server_conn, dbname):
                drop_database(server_conn, dbname)
            else:
                logger.info("--reset requested but database '%s' does not exist; skipping drop", dbname)

        # Create DB only if needed
        if not database_exists(server_conn, dbname):
            create_database(server_conn, dbname)
        else:
            logger.info("Database '%s' already exists — skipping creation", dbname)
    finally:
        server_conn.close()

    # ------------------------------------------------------------------
    # Step 2: application-level connection (run migrations)
    # ------------------------------------------------------------------
    try:
        app_conn = psycopg2.connect(**params)
    except psycopg2.OperationalError as exc:
        logger.critical("Cannot connect to database '%s': %s", dbname, exc)
        sys.exit(1)

    try:
        run_migrations(app_conn, dry_run=args.dry_run)
    except (psycopg2.Error, FileNotFoundError) as exc:
        logger.error("Setup failed: %s", exc)
        app_conn.close()
        sys.exit(1)
    finally:
        app_conn.close()

    if args.dry_run:
        logger.info("Dry run complete — no changes were made")
    else:
        logger.info("Database setup complete")


if __name__ == "__main__":
    main()
