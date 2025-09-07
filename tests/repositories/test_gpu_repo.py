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
    # We need to insert some dummy cases to satisfy foreign key constraints
    with db_connection.transaction() as conn:
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("case_for_gpu_001", "/tmp/case1", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("case_to_release_001", "/tmp/case2", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("case_lock_1", "/tmp/case3", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("case_lock_2", "/tmp/case4", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("case_lock_3", "/tmp/case5", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("some_case", "/tmp/case6", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("another_case", "/tmp/case7", "pending"))
        conn.execute("INSERT INTO cases (case_id, case_path, status) VALUES (?, ?, ?)", ("multi_gpu_case", "/tmp/case8", "pending"))
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
    gpu_repo.update_resources([GPU_DATA_1])
    updated_gpu_data = GPU_DATA_1.copy()
    updated_gpu_data["memory_used"] = 8192
    gpu_repo.update_resources([updated_gpu_data])
    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu.memory_used == 8192

def test_assign_gpu_to_case(gpu_repo):
    """Tests assigning a GPU to a case."""
    case_id = "case_for_gpu_001"
    gpu_repo.update_resources([GPU_DATA_1])
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)
    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu.status == GpuStatus.ASSIGNED and gpu.assigned_case == case_id

def test_release_gpu(gpu_repo):
    """Tests releasing a GPU, making it idle."""
    case_id = "case_to_release_001"
    gpu_repo.update_resources([GPU_DATA_1])
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)
    gpu_repo.release_gpu(GPU_DATA_1["uuid"])
    gpu = gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"])
    assert gpu.status == GpuStatus.IDLE and gpu.assigned_case is None

def test_find_and_lock_available_gpu(gpu_repo):
    """Tests finding and locking an available GPU atomically."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    locked_gpu = gpu_repo.find_and_lock_available_gpu("case_lock_1", min_memory_mb=8000)
    assert locked_gpu['gpu_uuid'] == GPU_DATA_2["uuid"]
    gpu2 = gpu_repo.get_gpu_by_uuid(GPU_DATA_2["uuid"])
    assert gpu2.status == GpuStatus.ASSIGNED

def test_get_all_gpu_resources(gpu_repo):
    """Tests retrieving all GPU resources from the database."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    all_gpus = gpu_repo.get_all_gpu_resources()
    assert len(all_gpus) == 2

def test_get_available_gpu_count(gpu_repo):
    """Tests counting the number of available (idle) GPUs."""
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    assert gpu_repo.get_available_gpu_count() == 2
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], "some_case")
    assert gpu_repo.get_available_gpu_count() == 1

def test_release_all_for_case(gpu_repo):
    """Tests releasing all GPUs assigned to a specific case."""
    case_id = "multi_gpu_case"
    gpu_repo.update_resources([GPU_DATA_1, GPU_DATA_2])
    gpu_repo.assign_gpu_to_case(GPU_DATA_1["uuid"], case_id)
    gpu_repo.assign_gpu_to_case(GPU_DATA_2["uuid"], case_id)
    released_count = gpu_repo.release_all_for_case(case_id)
    assert released_count == 2
    assert gpu_repo.get_gpu_by_uuid(GPU_DATA_1["uuid"]).status == GpuStatus.IDLE
