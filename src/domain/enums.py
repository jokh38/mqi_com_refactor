# =====================================================================================
# Target File: src/domain/enums.py
# Source Reference: src/states.py
# =====================================================================================
"""Defines enumerations for statuses and modes used throughout the application."""

from enum import Enum


class CaseStatus(Enum):
    """Enumeration of possible case statuses."""
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    PROCESSING = "processing"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BeamStatus(Enum):
    """Enumeration of possible beam statuses.

    Mirrors CaseStatus but is specific to a beam's lifecycle.
    """
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    UPLOADING = "uploading"
    HPC_QUEUED = "hpc_queued"
    HPC_RUNNING = "hpc_running"
    DOWNLOADING = "downloading"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(Enum):
    """Enumeration of workflow steps."""
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    TPS_GENERATION = "tps_generation"
    HPC_SUBMISSION = "hpc_submission"
    SIMULATION_RUNNING = "simulation_running"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"


class GpuStatus(Enum):
    """Enumeration of GPU resource statuses."""
    IDLE = "idle"
    BUSY = "busy"
    ASSIGNED = "assigned"
    UNAVAILABLE = "unavailable"


class ProcessingMode(Enum):
    """Enumeration of processing modes."""
    LOCAL = "local"
    REMOTE = "remote"
    HYBRID = "hybrid"