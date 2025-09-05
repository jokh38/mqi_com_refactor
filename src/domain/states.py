# =====================================================================================
# Target File: src/domain/states.py
# Source Reference: src/states.py
# =====================================================================================

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.workflow_manager import WorkflowManager

from src.domain.enums import CaseStatus


class WorkflowState(ABC):
    """
    Abstract base class for workflow states implementing the State pattern.
    FROM: Migrated from original states.py state machine implementation.
    """

    @abstractmethod
    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Execute the current state and return the next state.
        
        Args:
            context: The workflow manager providing access to repositories and handlers
            
        Returns:
            The next state to transition to, or None to terminate.
        """
        pass

    @abstractmethod
    def get_state_name(self) -> str:
        """Return the human-readable name of this state."""
        pass

class InitialState(WorkflowState):
    """
    Initial state for new cases.
    FROM: Initial state logic from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform initial validation and setup.
        FROM: Initial validation logic from original workflow.
        """
        context.logger.info("Performing initial validation and setup.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.PREPROCESSING)

        # Example validation: Check for a specific file
        # required_file = context.case_path / "input.txt"
        # if not required_file.exists():
        #     raise FileNotFoundError(f"Required file not found: {required_file}")

        return PreprocessingState()

    def get_state_name(self) -> str:
        return "Initial Validation"

class PreprocessingState(WorkflowState):
    """
    Preprocessing state for case preparation.
    FROM: Preprocessing state from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform preprocessing tasks.
        FROM: Preprocessing logic from original workflow.
        """
        context.logger.info("Running preprocessing tasks.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.PROCESSING)

        # Example: Run a local command
        # result = context.local_handler.run_command("preprocess_script.sh", cwd=context.case_path)
        # if result.returncode != 0:
        #     raise Exception(f"Preprocessing failed: {result.stderr}")

        return ProcessingState()

    def get_state_name(self) -> str:
        return "Preprocessing"

class ProcessingState(WorkflowState):
    """
    Main processing state for case execution.
    FROM: Processing state from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Execute main processing tasks.
        FROM: Processing logic from original workflow.
        """
        context.logger.info("Running main processing tasks.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.POSTPROCESSING)

        # Example: GPU allocation and remote execution
        # with context.gpu_repo.allocate_gpu() as gpu:
        #     if not gpu:
        #         raise Exception("Failed to allocate GPU.")
        #     context.remote_handler.run_simulation(gpu)

        return PostprocessingState()

    def get_state_name(self) -> str:
        return "Processing"

class PostprocessingState(WorkflowState):
    """
    Postprocessing state for results handling.
    FROM: Postprocessing state from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> WorkflowState:
        """
        Perform postprocessing tasks.
        FROM: Postprocessing logic from original workflow.
        """
        context.logger.info("Running postprocessing tasks.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.COMPLETED)

        # Example: Clean up temporary files
        # context.local_handler.cleanup_directory(context.case_path / "temp")

        return CompletedState()

    def get_state_name(self) -> str:
        return "Postprocessing"

class CompletedState(WorkflowState):
    """
    Final completed state.
    FROM: Completion handling from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handle completion tasks.
        FROM: Completion logic from original workflow.
        """
        context.logger.info("Workflow completed successfully.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.COMPLETED)
        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Completed"

class FailedState(WorkflowState):
    """
    Failed state for error handling.
    FROM: Error handling from original states.py.
    """

    def execute(self, context: 'WorkflowManager') -> Optional[WorkflowState]:
        """
        Handle failure cleanup.
        FROM: Error handling logic from original workflow.
        """
        context.logger.error("Workflow entered failed state.")
        context.case_repo.update_case_status(context.case_id, CaseStatus.FAILED)

        # Example: Release any allocated resources
        # context.gpu_repo.release_all_for_case(context.case_id)

        return None  # Terminal state

    def get_state_name(self) -> str:
        return "Failed"