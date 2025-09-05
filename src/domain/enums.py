# =====================================================================================
# Target File: src/domain/enums.py
# Source Reference: src/states.py
# =====================================================================================

from enum import Enum, auto

class CaseStatus(Enum):
    """
    Enumeration of possible case statuses.
    FROM: Migrated from status strings used throughout the original codebase.
    """
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    PROCESSING = "processing"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class WorkflowStep(Enum):
    """
    Enumeration of workflow steps.
    FROM: Extracted from workflow logic in original codebase.
    REFACTORING NOTES: Aligned with WORKFLOW_STEPS in constants.py
    """
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    TPS_GENERATION = "tps_generation"
    HPC_SUBMISSION = "hpc_submission"
    SIMULATION_RUNNING = "simulation_running"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"

class GpuStatus(Enum):
    """
    Enumeration of GPU resource statuses.
    FROM: Status values from nvidia-smi parsing logic.
    """
    IDLE = "idle"
    BUSY = "busy"
    ASSIGNED = "assigned"
    UNAVAILABLE = "unavailable"

class ProcessingMode(Enum):
    """
    Enumeration of processing modes.
    FROM: Configuration options in original codebase.
    """
    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"