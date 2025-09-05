import os
import sqlite3

import pytest

from src.config.settings import DatabaseConfig
from src.database.connection import DatabaseConnection


@pytest.fixture
def db_config(temp_db):
    """Pytest fixture for providing a default DatabaseConfig."""
    return DatabaseConfig(db_path=temp_db)


@pytest.fixture
def logger():
    """Pytest fixture for providing a mock logger."""

    class MockLogger:
        def info(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

    return MockLogger()


@pytest.fixture(scope="function")
def temp_db(tmp_path):
    """Pytest fixture to create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    yield db_path
    if db_path.exists():
        os.remove(db_path)


@pytest.fixture(scope="function")
def db_connection(temp_db, db_config, logger):
    """Pytest fixture to create a DatabaseConnection instance."""
    conn = DatabaseConnection(db_path=temp_db, config=db_config, logger=logger)
    yield conn
    conn.close()
