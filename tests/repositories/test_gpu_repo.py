import unittest
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

# Add src to path to allow imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.repositories.gpu_repo import GpuRepository
from src.database.connection import DatabaseConnection
from src.domain.enums import GpuStatus
from src.domain.models import GpuResource
from src.config.settings import DatabaseConfig

class TestGpuRepository(unittest.TestCase):

    def setUp(self):
        """Set up an in-memory SQLite database for each test."""
        self.mock_logger = Mock()

        self.mock_config = DatabaseConfig(
            db_path=Path(":memory:"),
            timeout=5.0,
            journal_mode="WAL",
            synchronous="NORMAL",
            cache_size=-2000
        )

        self.db_connection = DatabaseConnection(
            db_path=Path(":memory:"),
            config=self.mock_config,
            logger=self.mock_logger
        )

        # The GpuRepository interacts with tables created by CaseRepository's setup,
        # so we rely on the init_db() call from DatabaseConnection to create everything.

        # We need to insert some dummy cases to satisfy foreign key constraints
        # when testing GPU assignment.
        with self.db_connection.transaction() as conn:
            conn.execute(
                "INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)",
                ("test_case_1", "/tmp/case1", "pending")
            )
            conn.execute(
                "INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)",
                ("test_case_2", "/tmp/case2", "pending")
            )

        self.repo = GpuRepository(self.db_connection, self.mock_logger)

    def tearDown(self):
        """Close the database connection after each test."""
        self.db_connection.close()

    def _create_fake_gpu_data(self, uuid="gpu-1"):
        return {
            "uuid": uuid,
            "name": "Test GPU",
            "memory_total": 8000,
            "memory_used": 1000,
            "memory_free": 7000,
            "temperature": 50,
            "utilization": 10
        }

    def test_update_resources_insert(self):
        """Test that update_resources inserts a new GPU if it doesn't exist."""
        gpu_data = [self._create_fake_gpu_data("gpu-new")]

        self.repo.update_resources(gpu_data)

        gpu = self.repo.get_gpu_by_uuid("gpu-new")
        self.assertIsNotNone(gpu)
        self.assertEqual(gpu.name, "Test GPU")
        self.assertEqual(gpu.status, GpuStatus.IDLE)

    def test_update_resources_update(self):
        """Test that update_resources updates an existing GPU."""
        gpu_data_initial = [self._create_fake_gpu_data("gpu-existing")]
        self.repo.update_resources(gpu_data_initial)

        gpu_data_updated = self._create_fake_gpu_data("gpu-existing")
        gpu_data_updated["memory_used"] = 5000
        gpu_data_updated["memory_free"] = 3000
        gpu_data_updated["temperature"] = 75

        self.repo.update_resources([gpu_data_updated])

        gpu = self.repo.get_gpu_by_uuid("gpu-existing")
        self.assertEqual(gpu.memory_used, 5000)
        self.assertEqual(gpu.temperature, 75)

    def test_assign_gpu_to_case_and_release(self):
        """Test assigning a GPU to a case and then releasing it."""
        gpu_uuid = "gpu-assign"
        case_id = "test_case_1"
        self.repo.update_resources([self._create_fake_gpu_data(gpu_uuid)])

        # Assign
        self.repo.assign_gpu_to_case(gpu_uuid, case_id)
        gpu = self.repo.get_gpu_by_uuid(gpu_uuid)
        self.assertEqual(gpu.status, GpuStatus.ASSIGNED)
        self.assertEqual(gpu.assigned_case, case_id)

        # Release
        self.repo.release_gpu(gpu_uuid)
        gpu = self.repo.get_gpu_by_uuid(gpu_uuid)
        self.assertEqual(gpu.status, GpuStatus.IDLE)
        self.assertIsNone(gpu.assigned_case)

    def test_find_and_lock_available_gpu(self):
        """Test finding and locking an available GPU."""
        # Add two GPUs, one with enough memory, one without
        gpu_good = self._create_fake_gpu_data("gpu-good")
        gpu_bad = self._create_fake_gpu_data("gpu-bad")
        gpu_bad["memory_free"] = 500 # Not enough
        self.repo.update_resources([gpu_good, gpu_bad])

        # Find and lock
        locked_gpu_uuid = self.repo.find_and_lock_available_gpu("test_case_1", min_memory_mb=1000)
        self.assertEqual(locked_gpu_uuid, "gpu-good")

        # Verify it's locked
        gpu = self.repo.get_gpu_by_uuid("gpu-good")
        self.assertEqual(gpu.status, GpuStatus.ASSIGNED)

        # Try to lock again, should fail
        another_lock = self.repo.find_and_lock_available_gpu("test_case_2", min_memory_mb=1000)
        self.assertIsNone(another_lock, "Should not be able to lock an already assigned GPU or find another suitable one.")

        # Release and try again
        self.repo.release_gpu("gpu-good")
        relocked_gpu_uuid = self.repo.find_and_lock_available_gpu("test_case_2", min_memory_mb=1000)
        self.assertEqual(relocked_gpu_uuid, "gpu-good")

    def test_get_all_gpu_resources(self):
        """Test retrieving all GPU resources."""
        gpus_in = [self._create_fake_gpu_data("gpu-1"), self._create_fake_gpu_data("gpu-2")]
        self.repo.update_resources(gpus_in)

        gpus_out = self.repo.get_all_gpu_resources()
        self.assertEqual(len(gpus_out), 2)
        self.assertIsInstance(gpus_out[0], GpuResource)

    def test_get_available_gpu_count(self):
        """Test counting the number of available GPUs."""
        gpus = [
            self._create_fake_gpu_data("gpu-1"),
            self._create_fake_gpu_data("gpu-2"),
            self._create_fake_gpu_data("gpu-3")
        ]
        self.repo.update_resources(gpus)
        self.assertEqual(self.repo.get_available_gpu_count(), 3)

        # Assign one
        self.repo.assign_gpu_to_case("gpu-1", "test_case_1")
        self.assertEqual(self.repo.get_available_gpu_count(), 2)

    def test_release_all_for_case(self):
        """Test releasing all GPUs assigned to a specific case."""
        case_id = "test_case_1"
        gpus = [
            self._create_fake_gpu_data("gpu-a"),
            self._create_fake_gpu_data("gpu-b"),
            self._create_fake_gpu_data("gpu-c")
        ]
        self.repo.update_resources(gpus)

        # Assign two GPUs to the same case
        self.repo.assign_gpu_to_case("gpu-a", case_id)
        self.repo.assign_gpu_to_case("gpu-b", case_id)
        self.repo.assign_gpu_to_case("gpu-c", "test_case_2") # Different case

        # Verify assignments
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-a").status, GpuStatus.ASSIGNED)
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-b").status, GpuStatus.ASSIGNED)
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-c").status, GpuStatus.ASSIGNED)
        self.assertEqual(self.repo.get_available_gpu_count(), 0)

        # Release all for case_id
        num_released = self.repo.release_all_for_case(case_id)

        self.assertEqual(num_released, 2)
        self.assertEqual(self.repo.get_available_gpu_count(), 2)
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-a").status, GpuStatus.IDLE)
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-b").status, GpuStatus.IDLE)
        # Check that the other GPU was not affected
        self.assertEqual(self.repo.get_gpu_by_uuid("gpu-c").status, GpuStatus.ASSIGNED)

if __name__ == '__main__':
    unittest.main()
