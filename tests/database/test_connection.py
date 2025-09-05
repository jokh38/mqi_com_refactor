import sqlite3

import pytest

from src.domain.errors import DatabaseError


def test_database_connection_initialization(db_connection, temp_db):
    """
    Tests that the DatabaseConnection initializes correctly, creates the
    database file, and sets up the connection.
    """
    assert temp_db.exists()
    assert db_connection._conn is not None
    assert isinstance(db_connection.connection, sqlite3.Connection)


def test_init_db_creates_tables_and_indexes(db_connection):
    """
    Tests that the init_db method correctly creates all tables and indexes.
    """
    with db_connection.transaction() as conn:
        cursor = conn.cursor()

        # Check for tables
        tables = ["cases", "gpu_resources", "workflow_steps"]
        for table in tables:
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            assert cursor.fetchone() is not None, f"Table '{table}' not created."

        # Check for indexes
        indexes = [
            "idx_cases_status",
            "idx_cases_updated",
            "idx_gpu_status",
            "idx_workflow_case",
        ]
        for index in indexes:
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index}'"
            )
            assert cursor.fetchone() is not None, f"Index '{index}' not created."


def test_transaction_commit(db_connection):
    """
    Tests that a successful transaction commits the changes to the database.
    """
    test_case_id = "test_case_001"
    with db_connection.transaction() as conn:
        conn.execute(
            "INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)",
            (test_case_id, "/path/to/case", "PENDING"),
        )

    # Verify the data was committed by checking in a new transaction
    with db_connection.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?", (test_case_id,))
        result = cursor.fetchone()
        assert result is not None
        assert result["case_id"] == test_case_id


def test_transaction_rollback(db_connection):
    """
    Tests that a failing transaction rolls back the changes.
    """
    test_case_id = "test_case_002"
    try:
        with db_connection.transaction() as conn:
            conn.execute(
                "INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)",
                (test_case_id, "/path/to/case", "PENDING"),
            )
            # Intentionally raise an exception to trigger a rollback
            raise ValueError("Simulating a failure")
    except ValueError:
        pass  # Expected exception

    # Verify that the data was rolled back
    with db_connection.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?", (test_case_id,))
        result = cursor.fetchone()
        assert result is None


def test_close_connection(db_connection):
    """
    Tests that the close method properly closes the connection.
    """
    db_connection.close()
    assert db_connection._conn is None
    with pytest.raises(DatabaseError, match="Database connection is not established"):
        _ = db_connection.connection


def test_connection_property_raises_error_when_closed(db_connection):
    """
    Tests that the connection property raises a DatabaseError if accessed
    after closing.
    """
    db_connection.close()
    with pytest.raises(DatabaseError, match="Database connection is not established"):
        _ = db_connection.connection
