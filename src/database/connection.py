# =====================================================================================
# Target File: src/database/connection.py
# Source Reference: src/database_handler.py (connection and transaction management)
# =====================================================================================

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from src.config.settings import DatabaseConfig
from src.domain.errors import DatabaseError
from src.infrastructure.logging_handler import StructuredLogger


class DatabaseConnection:
    """
    Manages SQLite database connections, transactions, and schema initialization.

    FROM: Extracts connection, transaction, and schema management responsibilities
          from the original `DatabaseHandler` class in `database_handler.py`.
    REFACTORING NOTES: Follows Single Responsibility Principle by handling only
                      connection management and schema initialization.
    """

    def __init__(self, db_path: Path, config: DatabaseConfig, logger: StructuredLogger):
        """
        Initializes the database connection manager.

        Args:
            db_path: Path to the SQLite database file
            config: Database configuration settings
            logger: Logger for recording database events
        """
        self.db_path = db_path
        self.config = config
        self.logger = logger
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

        # Create database directory if it doesn't exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize connection and schema
        self._connect()
        self.init_db()

    def _connect(self) -> None:
        """
        Establishes connection to SQLite database with configuration settings.
        FROM: Connection establishment logic from original `__init__` method.
        """
        try:
            self._conn = sqlite3.connect(
                str(self.db_path), timeout=self.config.timeout, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row

            # Apply configuration settings
            self._conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
            self._conn.execute(f"PRAGMA synchronous = {self.config.synchronous}")
            self._conn.execute(f"PRAGMA cache_size = {self.config.cache_size}")

            self.logger.info(
                "Database connection established",
                {
                    "db_path": str(self.db_path),
                    "journal_mode": self.config.journal_mode,
                    "synchronous": self.config.synchronous,
                },
            )

        except sqlite3.Error as e:
            self.logger.error(
                "Failed to connect to database",
                {"db_path": str(self.db_path), "error": str(e)},
            )
            raise DatabaseError(f"Failed to connect to database: {e}")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for handling database transactions with thread-safe locking.
        This implementation is re-entrant and allows for nested transactions.

        FROM: Migrated from the `transaction` method in original `database_handler.py`.
        REFACTORING NOTES: Maintains the same transaction safety guarantees.

        Yields:
            The database connection for executing queries within the transaction
        """
        with self._lock:
            if not self._conn:
                raise DatabaseError("Database connection is not established")

            if self._conn.in_transaction:
                # Already in a transaction, just yield the connection
                yield self._conn
                return

            try:
                # Start a new transaction
                self._conn.execute("BEGIN")
                yield self._conn
                # Commit if no exceptions
                self._conn.commit()

            except Exception as e:
                # Rollback on any error
                self._conn.rollback()
                self.logger.error("Transaction failed, rolling back", {"error": str(e)})
                raise

    def init_db(self) -> None:
        """
        Initializes the database schema, creating all necessary tables and indexes.

        FROM: Migrated from the `init_db` method in original `database_handler.py`.
        REFACTORING NOTES: Maintains the same schema structure.
        """
        try:
            with self.transaction() as conn:
                # Create cases table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cases (
                        case_id TEXT PRIMARY KEY,
                        case_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        error_message TEXT,
                        assigned_gpu TEXT,
                        FOREIGN KEY (assigned_gpu)
                            REFERENCES gpu_resources (uuid)
                    )
                """
                )

                # Create gpu_resources table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gpu_resources (
                        uuid TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        memory_total INTEGER NOT NULL,
                        memory_used INTEGER NOT NULL,
                        memory_free INTEGER NOT NULL,
                        temperature INTEGER NOT NULL,
                        utilization INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        assigned_case TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (assigned_case)
                            REFERENCES cases (case_id)
                    )
                """
                )

                # Create workflow_steps table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id TEXT NOT NULL,
                        step TEXT NOT NULL,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        metadata TEXT,
                        FOREIGN KEY (case_id) REFERENCES cases (case_id)
                    )
                """
                )

                # Create indexes for performance
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cases_status ON cases (status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cases_updated ON "
                    "cases (updated_at)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gpu_status ON "
                    "gpu_resources (status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_workflow_case ON "
                    "workflow_steps (case_id)"
                )

            self.logger.info("Database schema initialized successfully")

        except sqlite3.Error as e:
            self.logger.error("Failed to initialize database schema", {"error": str(e)})
            raise DatabaseError(f"Failed to initialize database schema: {e}")

    def close(self) -> None:
        """
        Closes the database connection.
        FROM: Migrated from the `close` method in original `database_handler.py`.
        """
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                self.logger.info("Database connection closed")

    @property
    def connection(self) -> sqlite3.Connection:
        """
        Provides access to the raw connection for repository classes.

        Returns:
            The SQLite connection object
        """
        if not self._conn:
            raise DatabaseError("Database connection is not established")
        return self._conn
