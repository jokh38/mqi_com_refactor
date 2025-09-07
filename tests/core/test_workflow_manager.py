import pytest
from unittest.mock import MagicMock, patch

from src.core.workflow_manager import WorkflowManager
from src.domain.enums import CaseStatus
from src.domain.states import WorkflowState

class TestWorkflowManager:
    @pytest.fixture
    def mock_repos(self):
        case_repo = MagicMock()
        gpu_repo = MagicMock()
        return case_repo, gpu_repo

    @pytest.fixture
    def mock_handlers(self):
        local_handler = MagicMock()
        remote_handler = MagicMock()
        tps_generator = MagicMock()
        return local_handler, remote_handler, tps_generator

    @pytest.fixture
    def mock_logger(self):
        return MagicMock()

    @patch('src.core.workflow_manager.InitialState')
    def test_run_workflow_handles_exception_and_updates_status(
        self, mock_initial_state, mock_repos, mock_handlers, mock_logger
    ):
        # Arrange
        case_repo, gpu_repo = mock_repos
        local_handler, remote_handler, tps_generator = mock_handlers

        case_id = "test_case"
        case_path = MagicMock()
        error_message = "Something went wrong"

        # Mock the initial state to raise an exception
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.get_state_name.return_value = "MockState"
        mock_state.execute.side_effect = Exception(error_message)
        mock_initial_state.return_value = mock_state

        # Mock the get_case method to return a mock case with some progress
        mock_case = MagicMock()
        mock_case.progress = 25.0
        case_repo.get_case.return_value = mock_case

        manager = WorkflowManager(
            case_repo=case_repo,
            gpu_repo=gpu_repo,
            local_handler=local_handler,
            remote_handler=remote_handler,
            tps_generator=tps_generator,
            logger=mock_logger,
            id=case_id,
            path=case_path,
        )

        manager.run_workflow()

        # Assert
        # The error handling in WorkflowManager now calls update_beam_status
        from src.domain.enums import BeamStatus
        case_repo.update_beam_status.assert_called_once_with(
            case_id,
            BeamStatus.FAILED,
            error_message=error_message
        )
