# =====================================================================================
# Target File: src/repositories/gpu_repo.py
# Source Reference: src/database_handler.py (gpu_resources table operations)
# =====================================================================================

from typing import Optional, List, Dict, Any
from datetime import datetime

from src.repositories.base import BaseRepository
from src.database.connection import DatabaseConnection
from src.infrastructure.logging_handler import StructuredLogger
from src.domain.enums import GpuStatus
from src.domain.models import GpuResource
from src.domain.errors import GpuResourceError

class GpuRepository(BaseRepository):
    """
    Manages CRUD operations for the 'gpu_resources' table and handles GPU allocation/deallocation.
    
    FROM: Extracts all GPU-related database methods from the original `database_handler.py`.
    REFACTORING NOTES: Separates GPU data persistence from nvidia-smi parsing logic.
                      The parsing is now handled by `infrastructure/gpu_monitor.py`.
    """

    def __init__(self, db_connection: DatabaseConnection, logger: StructuredLogger):
        """
        Initializes the GPU repository with injected database connection.
        
        Args:
            db_connection: Database connection manager
            logger: Logger for recording operations
        """
        super().__init__(db_connection, logger)

    def update_resources(self, gpu_data: List[Dict[str, Any]]) -> None:
        """
        Updates GPU resources table with data from GPU monitor.
        
        FROM: The database update logic from `populate_gpu_resources_from_nvidia_smi` 
              in original `database_handler.py`.
        REFACTORING NOTES: Now receives clean, parsed data instead of raw nvidia-smi output.
                          The CSV parsing is handled by `infrastructure/gpu_monitor.py`.
        
        Args:
            gpu_data: List of dictionaries containing GPU information
        """
        self._log_operation("update_resources", count=len(gpu_data))
        
        for gpu in gpu_data:
            try:
                # Check if GPU exists
                existing_gpu = self._get_gpu_by_uuid(gpu['uuid'])
                
                if existing_gpu:
                    # Update existing GPU
                    self._update_existing_gpu(gpu)
                else:
                    # Insert new GPU
                    self._insert_new_gpu(gpu)
                    
            except Exception as e:
                self.logger.error("Failed to update GPU resource", {
                    "gpu_uuid": gpu.get('uuid', 'unknown'),
                    "error": str(e)
                })
                # Continue with other GPUs even if one fails

    def _get_gpu_by_uuid(self, uuid: str) -> Optional[Dict]:
        """Get GPU record by UUID."""
        query = "SELECT * FROM gpu_resources WHERE uuid = ?"
        return self._execute_query(query, (uuid,), fetch_one=True)

    def _update_existing_gpu(self, gpu_data: Dict[str, Any]) -> None:
        """Update existing GPU record."""
        query = """
            UPDATE gpu_resources 
            SET name = ?, memory_total = ?, memory_used = ?, memory_free = ?,
                temperature = ?, utilization = ?, last_updated = CURRENT_TIMESTAMP
            WHERE uuid = ?
        """
        
        self._execute_query(query, (
            gpu_data['name'],
            gpu_data['memory_total'],
            gpu_data['memory_used'], 
            gpu_data['memory_free'],
            gpu_data['temperature'],
            gpu_data['utilization'],
            gpu_data['uuid']
        ))

    def _insert_new_gpu(self, gpu_data: Dict[str, Any]) -> None:
        """Insert new GPU record."""
        query = """
            INSERT INTO gpu_resources 
            (uuid, name, memory_total, memory_used, memory_free, temperature, 
             utilization, status, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        
        self._execute_query(query, (
            gpu_data['uuid'],
            gpu_data['name'],
            gpu_data['memory_total'],
            gpu_data['memory_used'],
            gpu_data['memory_free'], 
            gpu_data['temperature'],
            gpu_data['utilization'],
            GpuStatus.IDLE.value  # Default status for new GPUs
        ))

    def assign_gpu_to_case(self, gpu_uuid: str, case_id: str) -> None:
        """
        Assigns a GPU to a specific case.
        
        FROM: GPU assignment logic from original `database_handler.py`.
        
        Args:
            gpu_uuid: UUID of the GPU to assign
            case_id: Case identifier to assign GPU to
        """
        self._log_operation("assign_gpu_to_case", gpu_uuid, case_id=case_id)
        
        query = """
            UPDATE gpu_resources 
            SET status = ?, assigned_case = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE uuid = ?
        """
        
        self._execute_query(query, (GpuStatus.ASSIGNED.value, case_id, gpu_uuid))
        
        self.logger.info("GPU assigned to case", {
            "gpu_uuid": gpu_uuid,
            "case_id": case_id
        })

    def release_gpu(self, gpu_uuid: str) -> None:
        """
        Releases a GPU, making it available again.
        
        FROM: GPU release logic from original `database_handler.py`.
        
        Args:
            gpu_uuid: UUID of the GPU to release
        """
        self._log_operation("release_gpu", gpu_uuid)
        
        query = """
            UPDATE gpu_resources 
            SET status = ?, assigned_case = NULL, last_updated = CURRENT_TIMESTAMP 
            WHERE uuid = ?
        """
        
        self._execute_query(query, (GpuStatus.IDLE.value, gpu_uuid))
        
        self.logger.info("GPU released", {"gpu_uuid": gpu_uuid})

    def find_and_lock_available_gpu(self, case_id: str, min_memory_mb: int = 1000) -> Optional[str]:
        """
        Atomically finds an idle GPU with sufficient memory and assigns it to a case.
        
        FROM: The atomic GPU allocation logic from original `database_handler.py`.
        REFACTORING NOTES: Maintains the same atomic transaction behavior.
        
        Args:
            case_id: Case identifier requesting GPU
            min_memory_mb: Minimum required memory in MB
            
        Returns:
            UUID of assigned GPU if successful, None otherwise
        """
        self._log_operation("find_and_lock_available_gpu", case_id, 
                          min_memory_mb=min_memory_mb)
        
        try:
            with self.db.transaction() as conn:
                # Find available GPU with sufficient memory
                query = """
                    SELECT uuid, memory_free 
                    FROM gpu_resources 
                    WHERE status = ? AND memory_free >= ?
                    ORDER BY memory_free DESC 
                    LIMIT 1
                """
                
                cursor = conn.execute(query, (GpuStatus.IDLE.value, min_memory_mb))
                gpu_row = cursor.fetchone()
                
                if not gpu_row:
                    self.logger.warning("No available GPU found", {
                        "case_id": case_id,
                        "min_memory_mb": min_memory_mb
                    })
                    return None
                
                gpu_uuid = gpu_row['uuid']
                
                # Assign GPU to case atomically
                update_query = """
                    UPDATE gpu_resources 
                    SET status = ?, assigned_case = ?, last_updated = CURRENT_TIMESTAMP 
                    WHERE uuid = ? AND status = ?
                """
                
                cursor = conn.execute(update_query, (
                    GpuStatus.ASSIGNED.value, 
                    case_id, 
                    gpu_uuid, 
                    GpuStatus.IDLE.value
                ))
                
                if cursor.rowcount != 1:
                    # GPU was taken by another process
                    self.logger.warning("GPU assignment race condition", {
                        "gpu_uuid": gpu_uuid,
                        "case_id": case_id
                    })
                    return None
                
                self.logger.info("GPU allocated successfully", {
                    "gpu_uuid": gpu_uuid,
                    "case_id": case_id,
                    "memory_free": gpu_row['memory_free']
                })
                
                return gpu_uuid
                
        except Exception as e:
            self.logger.error("Failed to allocate GPU", {
                "case_id": case_id,
                "error": str(e)
            })
            raise GpuResourceError(f"Failed to allocate GPU for case {case_id}: {e}")

    def get_all_gpu_resources(self) -> List[GpuResource]:
        """
        Retrieves detailed information for all tracked GPU resources.
        
        FROM: GPU resource retrieval from original `database_handler.py`.
        
        Returns:
            List of GpuResource objects
        """
        self._log_operation("get_all_gpu_resources")
        
        query = """
            SELECT uuid, name, memory_total, memory_used, memory_free, temperature, 
                   utilization, status, assigned_case, last_updated
            FROM gpu_resources
            ORDER BY name ASC
        """
        
        rows = self._execute_query(query, fetch_all=True)
        
        gpus = []
        for row in rows:
            gpus.append(GpuResource(
                uuid=row['uuid'],
                name=row['name'],
                memory_total=row['memory_total'],
                memory_used=row['memory_used'],
                memory_free=row['memory_free'],
                temperature=row['temperature'],
                utilization=row['utilization'],
                status=GpuStatus(row['status']),
                assigned_case=row['assigned_case'],
                last_updated=datetime.fromisoformat(row['last_updated']) if row['last_updated'] else None
            ))
        
        return gpus

    def get_gpu_by_uuid(self, uuid: str) -> Optional[GpuResource]:
        """
        Get specific GPU resource by UUID.
        
        Args:
            uuid: GPU UUID to retrieve
            
        Returns:
            GpuResource object if found, None otherwise
        """
        self._log_operation("get_gpu_by_uuid", uuid)
        
        query = """
            SELECT uuid, name, memory_total, memory_used, memory_free, temperature, 
                   utilization, status, assigned_case, last_updated
            FROM gpu_resources
            WHERE uuid = ?
        """
        
        row = self._execute_query(query, (uuid,), fetch_one=True)
        
        if row:
            return GpuResource(
                uuid=row['uuid'],
                name=row['name'],
                memory_total=row['memory_total'],
                memory_used=row['memory_used'],
                memory_free=row['memory_free'],
                temperature=row['temperature'],
                utilization=row['utilization'],
                status=GpuStatus(row['status']),
                assigned_case=row['assigned_case'],
                last_updated=datetime.fromisoformat(row['last_updated']) if row['last_updated'] else None
            )
        
        return None

    def get_available_gpu_count(self) -> int:
        """
        Get count of available (idle) GPUs.
        
        Returns:
            Number of idle GPUs
        """
        self._log_operation("get_available_gpu_count")
        
        query = "SELECT COUNT(*) as count FROM gpu_resources WHERE status = ?"
        row = self._execute_query(query, (GpuStatus.IDLE.value,), fetch_one=True)
        
        return row['count'] if row else 0
    
    def release_all_for_case(self, case_id: str) -> int:
        """
        Release all GPUs allocated to a specific case.
        
        Args:
            case_id: Case identifier
            
        Returns:
            Number of GPUs released
        """
        self._log_operation("release_all_for_case", case_id=case_id)
        
        with self.db_connection.transaction():
            # Update all GPUs assigned to this case
            query = """
                UPDATE gpu_resources 
                SET status = ?, assigned_case = NULL, last_updated = ?
                WHERE assigned_case = ?
            """
            
            result = self._execute_update(
                query,
                (GpuStatus.IDLE.value, datetime.utcnow().isoformat(), case_id)
            )
        
        self.logger.info("Released GPUs for case", {
            "case_id": case_id,
            "gpus_released": result
        })
        
        return result