import os
from pathlib import Path

import cv2

from utils.aws_cloud import upload_file_to_s3
from utils.loggers import create_logger
from utils.video_stream import capture_frame_with_opencv, get_direct_stream_url

logger = create_logger(__name__)

OUTPUT_FILENAME = "data/output.jpg"
STREAM_URL = os.getenv("ENV_STREAM_URL")
REGION_NAME = os.getenv("ENV_REGION_NAME")
BUCKET_NAME = os.getenv("ENV_BUCKET_NAME")


def main():
    """Main application function"""
    try:
        direct_stream_m3u8 = get_direct_stream_url(STREAM_URL)
        logger.info(
            f"Direct m3u8 stream extracted successfully from stream {STREAM_URL}"
        )

        frame = capture_frame_with_opencv(stream_url=direct_stream_m3u8)
        logger.info("Frame extracted successfully from m3u8 stream")

        if frame is not False:
            cv2.imwrite(OUTPUT_FILENAME, frame)

            upload_file_to_s3(
                file_name=OUTPUT_FILENAME,
                bucket_name=BUCKET_NAME,
                object_name=Path(OUTPUT_FILENAME).name,
                region_name=REGION_NAME,
            )
            Path(OUTPUT_FILENAME).unlink()
            return "Frame processed with success"
        else:
            return "No frame captured from the stream"

    except Exception as e:
        logger.info(f"Error extracting frame: {e}")
        return e


if __name__ == "__main__":
    main()
