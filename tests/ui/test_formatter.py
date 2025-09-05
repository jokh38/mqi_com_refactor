import pytest
from rich.text import Text

# Assuming CaseStatus and GpuStatus enums exist and have 'value' attribute
# In a real scenario, you might need to define mock enums or import them
from src.domain.enums import CaseStatus, GpuStatus
from src.ui.formatter import (
    get_case_status_text,
    get_gpu_status_text,
    format_memory_usage,
    format_utilization,
    format_temperature,
    format_progress_bar,
    format_elapsed_time,
    CASE_STATUS_COLORS,
    GPU_STATUS_COLORS,
)

# Helper to extract style from rich Text
def get_style(text: Text) -> str:
    return str(text.style)

@pytest.mark.parametrize(
    "status, expected_style",
    [
        (CaseStatus.PENDING, CASE_STATUS_COLORS[CaseStatus.PENDING]),
        (CaseStatus.PROCESSING, CASE_STATUS_COLORS[CaseStatus.PROCESSING]),
        (CaseStatus.COMPLETED, CASE_STATUS_COLORS[CaseStatus.COMPLETED]),
        (CaseStatus.FAILED, CASE_STATUS_COLORS[CaseStatus.FAILED]),
    ],
)
def test_get_case_status_text(status, expected_style):
    """Test that case status returns correct text and style."""
    text_obj = get_case_status_text(status)
    assert text_obj.plain == status.value.upper()
    assert get_style(text_obj) == expected_style

def test_get_case_status_text_unknown():
    """Test that an unknown case status returns a default style."""
    # Create a mock status
    class MockUnknownStatus:
        value = "UNKNOWN"

    text_obj = get_case_status_text(MockUnknownStatus)
    assert text_obj.plain == "UNKNOWN"
    assert get_style(text_obj) == "white"

@pytest.mark.parametrize(
    "status, expected_style",
    [
        (GpuStatus.IDLE, GPU_STATUS_COLORS[GpuStatus.IDLE]),
        (GpuStatus.ASSIGNED, GPU_STATUS_COLORS[GpuStatus.ASSIGNED]),
        (GpuStatus.UNAVAILABLE, GPU_STATUS_COLORS[GpuStatus.UNAVAILABLE]),
    ],
)
def test_get_gpu_status_text(status, expected_style):
    """Test that GPU status returns correct text and style."""
    text_obj = get_gpu_status_text(status)
    assert text_obj.plain == status.value.upper()
    assert get_style(text_obj) == expected_style

def test_format_memory_usage():
    """Test memory usage formatting."""
    text_obj = format_memory_usage(1024, 4096)
    assert text_obj.plain == "1024 / 4096 MB"
    assert get_style(text_obj) == "white"

@pytest.mark.parametrize(
    "util, expected_style",
    [(50, "green"), (75, "yellow"), (95, "red")],
)
def test_format_utilization(util, expected_style):
    """Test utilization formatting and color coding."""
    text_obj = format_utilization(util)
    assert text_obj.plain == f"{util}%"
    assert get_style(text_obj) == expected_style

@pytest.mark.parametrize(
    "temp, expected_style",
    [(60, "green"), (80, "yellow"), (90, "red")],
)
def test_format_temperature(temp, expected_style):
    """Test temperature formatting and color coding."""
    text_obj = format_temperature(temp)
    assert text_obj.plain == f"{temp}°C"
    assert get_style(text_obj) == expected_style

@pytest.mark.parametrize(
    "progress, expected_style_part",
    [
        (0, "yellow"),
        (10, "yellow"),
        (50, "cyan"),
        (80, "blue"),
        (100, "green"),
    ],
)
def test_format_progress_bar_style(progress, expected_style_part):
    """Test progress bar color coding."""
    text_obj = format_progress_bar(progress)
    # Check if the expected color is part of the style
    assert expected_style_part in get_style(text_obj)

def test_format_progress_bar_structure():
    """Test the structure of the progress bar string."""
    text_obj = format_progress_bar(50, width=10)
    # 5 filled, 5 empty
    assert "█████─────" in text_obj.plain
    assert "50.0%" in text_obj.plain

def test_format_progress_bar_none():
    """Test progress bar with None input."""
    text_obj = format_progress_bar(None)
    assert "0.0%" in text_obj.plain
    assert "yellow" in get_style(text_obj)

@pytest.mark.parametrize(
    "seconds, expected_str",
    [
        (3661, "1:01:01"),
        (90, "0:01:30"),
        (5, "0:00:05"),
        (None, "N/A"),
    ],
)
def test_format_elapsed_time(seconds, expected_str):
    """Test elapsed time formatting."""
    assert format_elapsed_time(seconds) == expected_str
