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
        return local_handler, remote_handler

    @pytest.fixture
    def mock_logger(self):
        return MagicMock()

    @patch('src.core.workflow_manager.InitialState')
    def test_run_workflow_handles_exception_and_updates_status(
        self, mock_initial_state, mock_repos, mock_handlers, mock_logger
    ):
        # Arrange
        case_repo, gpu_repo = mock_repos
        local_handler, remote_handler = mock_handlers

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
            logger=mock_logger,
            case_id=case_id,
            case_path=case_path,
        )

        manager.run_workflow()

        # Assert
        case_repo.update_case_status.assert_called_once_with(
            case_id,
            CaseStatus.FAILED,
            progress=25.0,
            error_message=error_message
        )
