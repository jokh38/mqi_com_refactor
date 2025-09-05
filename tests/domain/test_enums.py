from src.domain.enums import (
    CaseStatus,
    GpuStatus,
    ProcessingMode,
    WorkflowStep
)


def test_case_status_enum():
    """
    Tests that the CaseStatus enum has the correct members and values.
    """
    assert CaseStatus.PENDING.value == "pending"
    assert CaseStatus.PREPROCESSING.value == "preprocessing"
    assert CaseStatus.PROCESSING.value == "processing"
    assert CaseStatus.POSTPROCESSING.value == "postprocessing"
    assert CaseStatus.COMPLETED.value == "completed"
    assert CaseStatus.FAILED.value == "failed"
    assert CaseStatus.CANCELLED.value == "cancelled"

    expected_members = [
        "PENDING", "PREPROCESSING", "PROCESSING", "POSTPROCESSING",
        "COMPLETED", "FAILED", "CANCELLED"
    ]
    assert all(member in CaseStatus.__members__ for member in expected_members)
    assert len(CaseStatus) == len(expected_members)


def test_workflow_step_enum():
    """
    Tests that the WorkflowStep enum has the correct members and values.
    """
    assert WorkflowStep.PENDING.value == "pending"
    assert WorkflowStep.PREPROCESSING.value == "preprocessing"
    assert WorkflowStep.TPS_GENERATION.value == "tps_generation"
    assert WorkflowStep.HPC_SUBMISSION.value == "hpc_submission"
    assert WorkflowStep.SIMULATION_RUNNING.value == "simulation_running"
    assert WorkflowStep.POSTPROCESSING.value == "postprocessing"
    assert WorkflowStep.COMPLETED.value == "completed"
    assert WorkflowStep.FAILED.value == "failed"

    expected_members = [
        "PENDING", "PREPROCESSING", "TPS_GENERATION", "HPC_SUBMISSION",
        "SIMULATION_RUNNING", "POSTPROCESSING", "COMPLETED", "FAILED"
    ]
    assert all(
        member in WorkflowStep.__members__ for member in expected_members
    )
    assert len(WorkflowStep) == len(expected_members)


def test_gpu_status_enum():
    """
    Tests that the GpuStatus enum has the correct members and values.
    """
    assert GpuStatus.IDLE.value == "idle"
    assert GpuStatus.BUSY.value == "busy"
    assert GpuStatus.ASSIGNED.value == "assigned"
    assert GpuStatus.UNAVAILABLE.value == "unavailable"

    expected_members = ["IDLE", "BUSY", "ASSIGNED", "UNAVAILABLE"]
    assert all(member in GpuStatus.__members__ for member in expected_members)
    assert len(GpuStatus) == len(expected_members)


def test_processing_mode_enum():
    """
    Tests that the ProcessingMode enum has the correct members and values.
    """
    assert ProcessingMode.LOCAL.value == "local"
    assert ProcessingMode.REMOTE.value == "remote"
    assert ProcessingMode.HYBRID.value == "hybrid"

    expected_members = ["LOCAL", "REMOTE", "HYBRID"]
    assert all(
        member in ProcessingMode.__members__ for member in expected_members
    )
    assert len(ProcessingMode) == len(expected_members)
