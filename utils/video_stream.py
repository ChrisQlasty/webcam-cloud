import datetime

import cv2
import yt_dlp
from numpy.typing import NDArray

from utils.loggers import create_logger

logger = create_logger(__name__)


def get_direct_stream_url(youtube_url: str) -> str:
    """Get the direct stream URL from a YouTube video URL using yt-dlp."""

    ydl_opts = {
        "quiet": True,
        "forceurl": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info["url"]  # This is the .m3u8 stream URL


def capture_frame_with_opencv(stream_url: str) -> NDArray | bool:
    """Capture a frame from a video stream using OpenCV."""

    cap = None
    try:
        # Attempt to open the video stream
        cap = cv2.VideoCapture(stream_url)

        if not cap.isOpened():
            return False

        # Read one frame
        ret, frame = cap.read()

        if not ret:
            return False

        return frame

    except Exception as e:
        logger.error(f"Error capturing frame: {e}")
        return False
    finally:
        if cap is not None:
            cap.release()


def get_youtube_info(url: str) -> tuple[str | None, str | None]:
    """Fetches the title and description of a YouTube video using yt-dlp."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get("title")
            description = info_dict.get("description")
            current_year_str = str(datetime.datetime.now().year)
            title = title.split(current_year_str)[0]
            return title, description
    except Exception:
        return None, None
