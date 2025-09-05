
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
=======
import pytest
from src.repositories.gpu_repo import GpuRepository
from src.domain.enums import GpuStatus
from src.domain.models import GpuResource

# Sample GPU data for testing
GPU_DATA_1 = {
    "uuid": "GPU-111",
    "name": "NVIDIA GeForce RTX 3080",
    "memory_total": 10240,
    "memory_used": 1024,
    "memory_free": 9216,
    "temperature": 60,
    "utilization": 10,
}

GPU_DATA_2 = {
    "uuid": "GPU-222",
    "name": "NVIDIA GeForce RTX 3090",
    "memory_total": 24576,
    "memory_used": 2048,
    "memory_free": 22528,
    "temperature": 65,
    "utilization": 5,
}


@pytest.fixture
def gpu_repo(db_connection, logger):
    """Pytest fixture for creating a GpuRepository instance."""
    return GpuRepository(db_connection, logger)


def test_update_resources_insert(gpu_repo, db_connection):
    """Tests that new GPU resources are inserted correctly."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])

    with db_connection.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpu_resources")
        rows = cursor.fetchall()
        assert len(rows) == 2

        gpu1 = gpu_repo.get_gpu_by_uuid("GPU-111")
        assert gpu1 is not None
        assert gpu1.name == GPU_DATA_1["name"]
        assert gpu1.status == GpuStatus.IDLE


def test_update_resources_update(gpu_repo):
    """Tests that existing GPU resources are updated correctly."""
    # Initial insert
    gpu_repo.update_resources([GPU_DATA_1])

    # Update data
    updated_gpu_data = GPU_DATA_1.copy()
    updated_gpu_data["memory_used"] = 8192
    updated_gpu_data["memory_free"] = 2048
    updated_gpu_data["temperature"] = 75

    gpu_repo.update_resources([updated_gpu_data])

    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu is not None
    assert gpu.memory_used == 8192
    assert gpu.memory_free == 2048
    assert gpu.temperature == 75


def test_assign_gpu_to_case(gpu_repo):
    """Tests assigning a GPU to a case."""
    case_id = "case_for_gpu_001"
    gpu_repo.update_resources([GPU_DATA_1])

    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)

    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu is not None
    assert gpu.status == GpuStatus.ASSIGNED
    assert gpu.assigned_case == case_id


def test_release_gpu(gpu_repo):
    """Tests releasing a GPU, making it idle."""
    case_id = "case_to_release_001"
    gpu_repo.update_resources([GPU_DATA_1])
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)

    # Verify it's assigned
    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu.status == GpuStatus.ASSIGNED

    # Release it
    gpu_repo.release_gpu(GPU_DATA_1["uuid"])

    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu is not None
    assert gpu.status == GpuStatus.IDLE
    assert gpu.assigned_case is None


def test_find_and_lock_available_gpu(gpu_repo):
    """Tests finding and locking an available GPU atomically."""
    case_id_1 = "case_lock_1"
    case_id_2 = "case_lock_2"

    # Add two idle GPUs
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])

    # Find and lock the best GPU (GPU-222 has more memory)
    locked_gpu_uuid = gpu_repo.find_and_lock_available_gpu(
        case_id_1, min_memory_mb=8000
    )
    assert locked_gpu_uuid == GPU_DATA_2["uuid"]

    # Verify it's locked
    gpu2 = gpu_repo.get_gpu_by_uuid(GPU_DATA_2["uuid"])
    assert gpu2.status == GpuStatus.ASSIGNED
    assert gpu2.assigned_case == case_id_1

    # Try to lock another one, should get the remaining GPU
    locked_gpu_uuid_2 = gpu_repo.find_and_lock_available_gpu(
        case_id_2, min_memory_mb=8000
    )
    assert locked_gpu_uuid_2 == GPU_DATA_1["uuid"]

    # Try to lock one more, should get nothing
    no_gpu_locked = gpu_repo.find_and_lock_available_gpu(
        "case_lock_3", min_memory_mb=8000
    )
    assert no_gpu_locked is None


def test_get_all_gpu_resources(gpu_repo):
    """Tests retrieving all GPU resources from the database."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])

    all_gpus = gpu_repo.get_all_gpu_resources()
    assert len(all_gpus) == 2
    assert isinstance(all_gpus[0], GpuResource)

    uuids = {gpu.uuid for gpu in all_gpus}
    assert GPU_DATA_1["uuid"] in uuids
    assert GPU_DATA_2["uuid"] in uuids


def test_get_available_gpu_count(gpu_repo):
    """Tests counting the number of available (idle) GPUs."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    assert gpu_repo.get_available_gpu_count() == 2

    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], "some_case")
    assert gpu_repo.get_available_gpu_count() == 1

    gpu_repo.assign_gpu_to_case(GPU_DATA_2["uuid"], "another_case")
    assert gpu_repo.get_available_gpu_count() == 0


def test_release_all_for_case(gpu_repo):
    """Tests releasing all GPUs assigned to a specific case."""
    case_id = "multi_gpu_case"
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)
    gpu_repo.assign_gpu_to_case(GPU_DATA_2["uuid"], case_id)

    # Verify they are assigned
    assert gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"]).status == GpuStatus.ASSIGNED
    assert gpu_repo.get_gpu_by_uuid(GPU_DATA_2["uuid"]).status == GpuStatus.ASSIGNED

    # Release all for the case
    released_count = gpu_repo.release_all_for_case(case_id)
    assert released_count == 2

    # Verify they are now idle
    assert gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"]).status == GpuStatus.IDLE
    assert gpu_repo.get_gpu_by_uuid(GPU_DATA_2["uuid"]).status == GpuStatus.IDLE
