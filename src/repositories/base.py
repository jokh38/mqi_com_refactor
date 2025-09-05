from abc import ABC
from typing import Optional, Any

from src.database.connection import DatabaseConnection
from src.infrastructure.logging_handler import StructuredLogger


class BaseRepository(ABC):
    """
    Abstract base class for all repository implementations.

    FROM: Implements Repository Pattern as suggested in the refactoring plan
          to decouple data access from business logic.
    REFACTORING NOTES: Provides common database access patterns and error handling.
    """

    def __init__(self, db_connection: DatabaseConnection, logger: StructuredLogger):
        """
        Initialize repository with database connection and logger.

        Args:
            db_connection: The database connection manager
            logger: Logger for recording repository operations
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
        """
        Execute a database query with error handling and logging.

        Args:
            query: SQL query to execute
            params: Parameters for the query
            fetch_one: Whether to fetch one result
            fetch_all: Whether to fetch all results

        Returns:
            Query results based on fetch parameters
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
        """
        Log repository operations for debugging and monitoring.

        Args:
            operation: Description of the operation
            entity_id: ID of the entity being operated on
            **context: Additional context for logging
        """
        log_data = {"repository": self.__class__.__name__, "operation": operation}

        if entity_id:
            log_data["entity_id"] = entity_id

        log_data.update(context)

        self.logger.debug("Repository operation", log_data)