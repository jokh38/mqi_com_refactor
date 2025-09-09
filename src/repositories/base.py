"""!
@file base.py
@brief Contains the abstract base class for all repository implementations.
"""
from abc import ABC
from typing import Optional, Any

from src.database.connection import DatabaseConnection
from src.infrastructure.logging_handler import StructuredLogger


class BaseRepository(ABC):
    """!
    @brief Abstract base class for all repository implementations.
    @details This class provides common database access patterns and error handling.
    """

    def __init__(self, db_connection: DatabaseConnection, logger: StructuredLogger):
        """!
        @brief Initialize the repository with a database connection and logger.
        @param db_connection: The database connection manager.
        @param logger: The logger for recording repository operations.
        """
        self.db = db_connection
        self.logger = logger

    def _execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False,
        fetch_all: bool = False,
    ) -> Optional[Any]:
        """!
        @brief Execute a database query with error handling and logging.
        @param query: The SQL query to execute.
        @param params: The parameters for the query.
        @param fetch_one: Whether to fetch one result.
        @param fetch_all: Whether to fetch all results.
        @return The query results based on the fetch parameters.
        """
        try:
            with self.db.transaction() as conn:
                cursor = conn.execute(query, params)

                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    # For INSERT, UPDATE, DELETE, return the number of affected rows
                    return cursor.rowcount
                    
        except Exception as e:
            self.logger.error(
                f"Database query failed: {query}", {"error": str(e), "params": params}
            )
            raise

    def _log_operation(self, operation: str, entity_id: str = None, **context):
        """!
        @brief Log repository operations for debugging and monitoring.
        @param operation: A description of the operation.
        @param entity_id: The ID of the entity being operated on.
        @param **context: Additional context for logging.
        """
        log_data = {"repository": self.__class__.__name__, "operation": operation}

        if entity_id:
            log_data["entity_id"] = entity_id

        log_data.update(context)

        self.logger.debug("Repository operation", log_data)