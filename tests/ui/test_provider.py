import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from src.ui.provider import DashboardDataProvider
from src.domain.models import CaseData, GpuResource
from src.domain.enums import CaseStatus, GpuStatus

@pytest.fixture
def mock_repos(mocker):
    """Fixture to create mock repositories and logger."""
    mock_case_repo = MagicMock()
    mock_gpu_repo = MagicMock()
    mock_logger = MagicMock()
    return mock_case_repo, mock_gpu_repo, mock_logger

@pytest.fixture
def sample_raw_data():
    """Fixture to provide sample raw data returned by repositories."""
    case1_created = datetime.now() - timedelta(minutes=10)
    raw_cases = [
        CaseData(case_id="case_01", case_path=Path("/fake/case_01"), status=CaseStatus.PROCESSING, progress=50.5, assigned_gpu="gpu_A", created_at=case1_created),
        CaseData(case_id="case_02", case_path=Path("/fake/case_02"), status=CaseStatus.PENDING, progress=0.0, assigned_gpu=None, created_at=datetime.now()),
    ]
    raw_gpus = [
        GpuResource(uuid="gpu_A", name="NVIDIA 1", status=GpuStatus.ASSIGNED, assigned_case="case_01", memory_total=2000, memory_used=1000, memory_free=1000, utilization=80, temperature=70),
        GpuResource(uuid="gpu_B", name="NVIDIA 2", status=GpuStatus.IDLE, assigned_case=None, memory_total=2000, memory_used=10, memory_free=1990, utilization=5, temperature=40),
    ]
    return raw_cases, raw_gpus

def test_provider_initialization(mock_repos):
    """Test that the provider initializes correctly."""
    case_repo, gpu_repo, logger = mock_repos
    provider = DashboardDataProvider(case_repo, gpu_repo, logger)

    assert provider.case_repo is case_repo
    assert provider.gpu_repo is gpu_repo
    assert provider.logger is logger
    assert provider.get_system_stats() == {}
    assert provider.get_gpu_data() == []
    assert provider.get_active_cases_data() == []

def test_refresh_all_data_success(mock_repos, sample_raw_data):
    """Test the successful refresh of all data."""
    case_repo, gpu_repo, logger = mock_repos
    raw_cases, raw_gpus = sample_raw_data

    case_repo.get_all_active_cases.return_value = raw_cases
    gpu_repo.get_all_gpu_resources.return_value = raw_gpus

    provider = DashboardDataProvider(case_repo, gpu_repo, logger)
    provider.refresh_all_data()

    # Verify logs
    logger.info.assert_called_with("Refreshing all dashboard data")

    # Verify processed case data
    active_cases = provider.get_active_cases_data()
    assert len(active_cases) == 2
    assert active_cases[0]["case_id"] == "case_01"
    assert active_cases[0]["status"] == CaseStatus.PROCESSING
    assert active_cases[0]["progress"] == 50.5
    assert active_cases[1]["case_id"] == "case_02"

    # Verify processed GPU data
    gpu_data = provider.get_gpu_data()
    assert len(gpu_data) == 2
    assert gpu_data[0]["uuid"] == "gpu_A"
    assert gpu_data[0]["status"] == GpuStatus.ASSIGNED
    assert gpu_data[1]["uuid"] == "gpu_B"
    assert gpu_data[1]["status"] == GpuStatus.IDLE

    # Verify system stats
    stats = provider.get_system_stats()
    assert stats["total_cases"] == 2
    assert stats[CaseStatus.PROCESSING.value] == 1
    assert stats[CaseStatus.PENDING.value] == 1
    assert stats[CaseStatus.COMPLETED.value] == 0 # Check that a non-present status is 0
    assert stats["total_gpus"] == 2
    assert stats["available_gpus"] == 1
    assert stats["last_update"] is not None

def test_refresh_all_data_failure(mock_repos):
    """Test data refresh when a repository raises an exception."""
    case_repo, gpu_repo, logger = mock_repos

    # Configure one of the repos to fail
    gpu_repo.get_all_gpu_resources.side_effect = Exception("Database connection failed")

    provider = DashboardDataProvider(case_repo, gpu_repo, logger)
    provider.refresh_all_data()

    # Verify error log
    logger.error.assert_called_once()
    assert "Failed to refresh dashboard data" in logger.error.call_args[0][0]

    # Verify data is cleared to prevent stale display
    assert provider.get_system_stats() == {}
    assert provider.get_gpu_data() == []
    assert provider.get_active_cases_data() == []

def test_private_process_case_data(mock_repos, sample_raw_data):
    """Test the internal case data processing logic."""
    case_repo, gpu_repo, logger = mock_repos
    raw_cases, _ = sample_raw_data

    provider = DashboardDataProvider(case_repo, gpu_repo, logger)
    processed_data = provider._process_case_data(raw_cases)

    assert len(processed_data) == 2
    assert processed_data[0]['case_id'] == 'case_01'
    assert 'elapsed_time' in processed_data[0]
    assert processed_data[0]['elapsed_time'] > 590 # Approx 10 minutes

def test_private_process_gpu_data(mock_repos, sample_raw_data):
    """Test the internal GPU data processing logic."""
    case_repo, gpu_repo, logger = mock_repos
    _, raw_gpus = sample_raw_data

    provider = DashboardDataProvider(case_repo, gpu_repo, logger)
    processed_data = provider._process_gpu_data(raw_gpus)

    assert len(processed_data) == 2
    assert processed_data[0]['uuid'] == 'gpu_A'
    assert processed_data[0]['name'] == 'NVIDIA 1'
    assert processed_data[0]['memory_used'] == 1000

def test_private_calculate_system_metrics(mock_repos, sample_raw_data):
    """Test the internal system metrics calculation."""
    case_repo, gpu_repo, logger = mock_repos
    raw_cases, raw_gpus = sample_raw_data

    provider = DashboardDataProvider(case_repo, gpu_repo, logger)
    metrics = provider._calculate_system_metrics(raw_cases, raw_gpus)

    assert metrics['total_cases'] == 2
    assert metrics['total_gpus'] == 2
    assert metrics['available_gpus'] == 1

    # Check that all statuses are present and counts are correct
    assert metrics[CaseStatus.PENDING.value] == 1
    assert metrics[CaseStatus.PROCESSING.value] == 1
    assert metrics[CaseStatus.COMPLETED.value] == 0
    # Check that all keys from the enum exist in the metrics
    for status in CaseStatus:
        assert status.value in metrics
