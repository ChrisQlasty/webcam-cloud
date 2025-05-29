import os

import numpy as np
import pytest

from utils.video_stream import capture_frame_with_opencv, get_direct_stream_url

STREAM_URL = os.getenv("ENV_STREAM_URL")


@pytest.fixture
def mock_youtube_url():
    return STREAM_URL


@pytest.fixture
def mock_stream_url():
    return get_direct_stream_url(STREAM_URL)


@pytest.fixture
def mock_invalid_stream_url():
    return "https://www.invalid-url.com"


def test_get_direct_stream_url_success(mock_youtube_url: str):
    """Test retrieving a direct stream URL successfully."""
    stream_url = get_direct_stream_url(mock_youtube_url)
    assert isinstance(stream_url, str), "Stream URL is not a string"
    assert stream_url.startswith("http"), "Stream URL is not valid"


def test_get_direct_stream_url_failure(mock_invalid_stream_url: str):
    """Test retrieving a direct stream URL with an invalid YouTube URL."""
    with pytest.raises(Exception):
        get_direct_stream_url(mock_invalid_stream_url)


def test_capture_frame_with_opencv_success(mock_stream_url: str):
    """Test capturing a frame successfully."""
    frame = capture_frame_with_opencv(mock_stream_url)
    assert frame is not False, "Failed to capture frame"
    assert isinstance(frame, np.ndarray), "Captured frame is not a valid np.ndarray"
    assert frame.ndim == 3, "Captured frame does not have 3 dimensions (HxWxC)"


def test_capture_frame_with_opencv_failure(mock_invalid_stream_url: str):
    """Test capturing a frame with an invalid stream URL."""
    frame = capture_frame_with_opencv(mock_invalid_stream_url)
    assert frame is False, "Expected failure for invalid stream URL"
