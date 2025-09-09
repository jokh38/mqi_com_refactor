# =====================================================================================
# Target File: src/core/workflow_manager.py
# Source Reference: src/workflow_manager.py, src/worker.py
# =====================================================================================
"""!
@file workflow_manager.py
@brief Manages and orchestrates the entire workflow for a case using a state pattern.
"""

from typing import Optional, Any, Dict
from pathlib import Path

from src.repositories.case_repo import CaseRepository
from src.repositories.gpu_repo import GpuRepository
from src.handlers.local_handler import LocalHandler
from src.handlers.remote_handler import RemoteHandler
from src.infrastructure.logging_handler import StructuredLogger
from src.core.tps_generator import TpsGenerator
from src.domain.enums import CaseStatus, BeamStatus
from src.domain.states import WorkflowState, InitialState


class WorkflowManager:
    """!
    @brief Manages and orchestrates the entire workflow for a case according to the State pattern.
    @details This class is responsible for executing each `State` and transitioning to the next,
             using the injected `repositories` and `handlers`.
    """

    def __init__(
        self,
        case_repo: CaseRepository,
        gpu_repo: GpuRepository,
        local_handler: LocalHandler,
        remote_handler: RemoteHandler,
        tps_generator: TpsGenerator,
        logger: StructuredLogger,
        id: str,
        path: Path,
    ):
        """!
        @brief Initializes the workflow manager with all required dependencies.
        @param case_repo: The case repository for database access.
        @param gpu_repo: The GPU repository for database access.
        @param local_handler: The handler for local command execution.
        @param remote_handler: The handler for remote command execution.
        @param tps_generator: The TPS generator service.
        @param logger: The structured logger.
        @param id: The unique identifier for the case or beam.
        @param path: The path to the case or beam directory.
        """
        self.case_repo = case_repo
        self.gpu_repo = gpu_repo
        self.local_handler = local_handler
        self.remote_handler = remote_handler
        self.tps_generator = tps_generator
        self.logger = logger
        self.id = id
        self.path = path
        self.current_state: Optional[WorkflowState] = InitialState()
        self.shared_context: Dict[str, Any] = {}

    def run_workflow(self) -> None:
        """!
        @brief Executes the complete workflow by managing state transitions.
        """
        self.logger.info(f"Starting workflow for: {self.id}")

        while self.current_state:
            state_name = self.current_state.get_state_name()
            self.logger.info(f"Executing state: {state_name}")

            try:
                next_state = self.current_state.execute(self)
                self._transition_to_next_state(next_state)
            except Exception as e:
                self._handle_workflow_error(e, f"Error during state: {state_name}")
                break

        self.logger.info(f"Workflow finished for: {self.id}")

    def _transition_to_next_state(self, next_state: WorkflowState) -> None:
        """!
        @brief Handles the transition from the current state to the next state.
        @param next_state: The next state in the workflow.
        """
        if next_state:
            self.logger.info(f"Transitioning from {self.current_state.get_state_name()} to {next_state.get_state_name()}")
        else:
            self.logger.info(f"Transitioning from {self.current_state.get_state_name()} to None (workflow end)")

        self.current_state = next_state

    def _handle_workflow_error(self, error: Exception, context: str) -> None:
        """!
        @brief Handles errors that occur during workflow execution.
        @param error: The exception that occurred.
        @param context: A string describing the context in which the error occurred.
        """
        self.logger.error(
            "Workflow error occurred",
            {
                "id": self.id,
                "context": context,
                "error": str(error),
                "error_type": type(error).__name__,
                "current_state": self.current_state.get_state_name() if self.current_state else "None"
            }
        )

        try:
            # This logic is now beam-specific. The calling state should handle status updates.
            # For now, we'll assume the worker is for a beam and try to update beam status.
            # This part will need more refinement when states are refactored.
            self.case_repo.update_beam_status(
                self.id,
                BeamStatus.FAILED,
                error_message=str(error),
            )
            self.logger.info(f"Beam status updated to FAILED for: {self.id}")
        except Exception as db_error:
            self.logger.error(
                "Failed to update status during error handling",
                {
                    "id": self.id,
                    "db_error": str(db_error)
                }
            )

        self.current_state = None # Stop the workflow