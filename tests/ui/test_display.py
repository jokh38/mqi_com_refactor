import pytest
from unittest.mock import MagicMock, patch, call

# Mock the rich library before it's imported by the module we're testing
@pytest.fixture(autouse=True)
def mock_rich(mocker):
    mocker.patch('src.ui.display.Console')
    mocker.patch('src.ui.display.Layout')
    mocker.patch('src.ui.display.Live')
    mocker.patch('src.ui.display.Panel')
    mocker.patch('src.ui.display.Table')
    mocker.patch('src.ui.display.Text')

@pytest.fixture
def mock_provider(mocker):
    """Fixture to create a mock DashboardDataProvider."""
    provider = MagicMock()
    provider.get_system_stats.return_value = {
        'total_cases': 5, 'pending': 2, 'processing': 3,
        'total_gpus': 4, 'available_gpus': 1
    }
    provider.get_gpu_data.return_value = [{'uuid': 'gpu1', 'name': 'GPU 1', 'status': 'idle', 'memory_used': 100, 'memory_total': 1024, 'utilization': 50, 'temperature': 60}]
    provider.get_active_cases_data.return_value = [{'case_id': 'case1', 'status': 'processing', 'progress': 50, 'assigned_gpu': 'gpu1', 'elapsed_time': 300}]
    return provider

@pytest.fixture
def mock_logger(mocker):
    """Fixture to create a mock StructuredLogger."""
    return MagicMock()

@pytest.fixture
def display_manager(mock_provider, mock_logger):
    """Fixture to create a DisplayManager with mocked dependencies."""
    # Since we are mocking rich, we need to import DisplayManager after mocks are set up
    from src.ui.display import DisplayManager
    return DisplayManager(provider=mock_provider, logger=mock_logger)

def test_display_manager_initialization(display_manager, mock_provider, mock_logger):
    """Test that the DisplayManager initializes correctly."""
    from src.ui.display import Layout
    assert display_manager.provider is mock_provider
    assert display_manager.logger is mock_logger
    assert display_manager.running is False
    # Check that the layout was created
    assert Layout.call_count > 0

def test_create_layout(display_manager):
    """Test the structure of the created layout."""
    from src.ui.display import Layout
    # Reset mock to only count calls within this test
    Layout.reset_mock()
    layout = display_manager._create_layout()

    # Check that the main layout and splits are created
    Layout.assert_has_calls([
        call(name='root'),
        call().split(Layout(), Layout(), Layout()),
        call().__getitem__('main').split_row(Layout(), Layout())
    ], any_order=True)

@patch('src.ui.display.threading')
def test_start(mock_threading, display_manager, mock_logger):
    """Test the start method."""
    display_manager.start()

    assert display_manager.running is True
    # Check that Live object was created and started
    display_manager.live.start.assert_called_once()

    # Check that a thread was created and started
    mock_threading.Thread.assert_called_once_with(target=display_manager._update_loop, daemon=True)
    mock_threading.Thread().start.assert_called_once()
    mock_logger.info.assert_called_with("Display manager started.")

def test_start_already_running(display_manager, mock_logger):
    """Test that start does nothing if already running."""
    display_manager.running = True
    display_manager.start()
    mock_logger.warning.assert_called_with("Display manager is already running.")
    assert display_manager.live is None # Live should not be initialized

@patch('src.ui.display.threading.Thread')
def test_stop(mock_thread, display_manager, mock_logger):
    """Test the stop method."""
    # Pretend it was running
    display_manager.running = True
    display_manager._update_thread = mock_thread
    live_mock = MagicMock()
    display_manager.live = live_mock

    display_manager.stop()

    assert display_manager.running is False
    mock_thread.join.assert_called_once()
    live_mock.stop.assert_called_once()
    mock_logger.info.assert_called_with("Display manager stopped.")

def test_update_display(display_manager, mock_provider):
    """Test the main display update method."""
    # Mock the panel creation methods to isolate update_display's logic
    display_manager._create_system_stats_panel = MagicMock()
    display_manager._create_gpu_panel = MagicMock()
    display_manager._create_cases_panel = MagicMock()

    # The `live` object is only created during start(), so mock it for this test
    display_manager.live = MagicMock()

    display_manager.update_display()

    # Check that provider was called
    mock_provider.get_system_stats.assert_called_once()
    mock_provider.get_gpu_data.assert_called_once()
    mock_provider.get_active_cases_data.assert_called_once()

    # Check that layout sections are updated
    assert display_manager.layout["header"].update.called
    assert display_manager.layout["system_stats"].update.called
    assert display_manager.layout["gpu_resources"].update.called
    assert display_manager.layout["right"].update.called
    assert display_manager.layout["footer"].update.called

    # Check that live refresh was called
    display_manager.live.refresh.assert_called_once()

@patch('src.ui.display.formatter')
def test_create_panels(mock_formatter, display_manager, mock_provider):
    """Test the individual panel creation methods."""
    from src.ui.display import Panel, Table

    # Test stats panel
    stats_data = mock_provider.get_system_stats()
    display_manager._create_system_stats_panel(stats_data)
    Panel.assert_called()
    Table.assert_called()
    # Check a sample row was added
    Table().add_row.assert_any_call("Total Active", str(stats_data['total_cases']))

    # Test GPU panel
    gpu_data = mock_provider.get_gpu_data()
    display_manager._create_gpu_panel(gpu_data)
    mock_formatter.get_gpu_status_text.assert_called()

    # Test cases panel
    cases_data = mock_provider.get_active_cases_data()
    display_manager._create_cases_panel(cases_data)
    mock_formatter.get_case_status_text.assert_called()
    mock_formatter.format_progress_bar.assert_called()
    mock_formatter.format_elapsed_time.assert_called()
