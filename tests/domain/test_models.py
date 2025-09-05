from dataclasses import is_dataclass
from pathlib import Path
from datetime import datetime

from src.domain.models import (
    CaseData,
    GpuResource,
    WorkflowStepRecord,
    SystemStats,
)
from src.domain.enums import CaseStatus, GpuStatus, WorkflowStep


def test_casedata_model():
    """
    Tests the CaseData dataclass for correct instantiation and attributes.
    """
    now = datetime.now()
    case_path = Path("/tmp/case-123")

    # Test with all fields
    case = CaseData(
        case_id="case-123",
        case_path=case_path,
        status=CaseStatus.PENDING,
        progress=0.0,
        created_at=now,
        updated_at=now,
        error_message="An error.",
        assigned_gpu="gpu-uuid-1"
    )

    assert is_dataclass(case)
    assert case.case_id == "case-123"
    assert case.case_path == case_path
    assert case.status == CaseStatus.PENDING
    assert case.progress == 0.0
    assert case.created_at == now
    assert case.updated_at == now
    assert case.error_message == "An error."
    assert case.assigned_gpu == "gpu-uuid-1"

    # Test with only required fields
    case_minimal = CaseData(
        case_id="case-456",
        case_path=Path("/tmp/case-456"),
        status=CaseStatus.COMPLETED,
        progress=100.0,
        created_at=now,
    )
    assert case_minimal.updated_at is None
    assert case_minimal.error_message is None
    assert case_minimal.assigned_gpu is None


def test_gpuresource_model():
    """
    Tests the GpuResource dataclass for correct instantiation.
    """
    now = datetime.now()

    # Test with all fields
    gpu = GpuResource(
        uuid="gpu-uuid-1",
        name="GeForce RTX 3090",
        memory_total=24576,
        memory_used=1024,
        memory_free=23552,
        temperature=65,
        utilization=50,
        status=GpuStatus.BUSY,
        assigned_case="case-123",
        last_updated=now
    )

    assert is_dataclass(gpu)
    assert gpu.uuid == "gpu-uuid-1"
    assert gpu.status == GpuStatus.BUSY
    assert gpu.assigned_case == "case-123"
    assert gpu.last_updated == now

    # Test with only required fields
    gpu_minimal = GpuResource(
        uuid="gpu-uuid-2",
        name="GeForce RTX 4090",
        memory_total=24576,
        memory_used=0,
        memory_free=24576,
        temperature=30,
        utilization=0,
        status=GpuStatus.IDLE,
    )
    assert gpu_minimal.assigned_case is None
    assert gpu_minimal.last_updated is None


def test_workflowsteprecord_model():
    """
    Tests the WorkflowStepRecord dataclass for correct instantiation.
    """
    now = datetime.now()

    # Test with all fields
    record = WorkflowStepRecord(
        case_id="case-123",
        step=WorkflowStep.PREPROCESSING,
        status="completed",
        started_at=now,
        completed_at=now,
        error_message="No error.",
        metadata={"key": "value"}
    )

    assert is_dataclass(record)
    assert record.case_id == "case-123"
    assert record.step == WorkflowStep.PREPROCESSING
    assert record.status == "completed"
    assert record.metadata == {"key": "value"}

    # Test with only required fields
    record_minimal = WorkflowStepRecord(
        case_id="case-456",
        step=WorkflowStep.FAILED,
        status="failed",
        started_at=now,
    )
    assert record_minimal.completed_at is None
    assert record_minimal.error_message is None
    assert record_minimal.metadata is None


def test_systemstats_model():
    """
    Tests the SystemStats dataclass for correct instantiation.
    """
    now = datetime.now()

    stats = SystemStats(
        total_cases=10,
        active_cases=2,
        completed_cases=5,
        failed_cases=3,
        total_gpus=4,
        available_gpus=1,
        busy_gpus=3,
        last_updated=now
    )

    assert is_dataclass(stats)
    assert stats.total_cases == 10
    assert stats.available_gpus == 1
    assert stats.last_updated == now
