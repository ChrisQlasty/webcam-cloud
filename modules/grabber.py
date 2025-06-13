import os
import time
from datetime import datetime
from pathlib import Path

import click
import cv2

from utils.aws_cloud import upload_file_to_s3
from utils.loggers import create_logger
from utils.video_stream import capture_frame_with_opencv, get_direct_stream_url

logger = create_logger(__name__)

TMP_OUTPUT_FILENAME = "data/output.jpg"
STREAM_URL = os.getenv("ENV_STREAM_URL")
REGION_NAME = os.getenv("TF_VAR_region")
BUCKET_NAME = os.getenv("TF_VAR_input_bucket")


@click.command()
@click.option(
    "--num-frames", default=12, help="Number of frames to capture", show_default=True
)
@click.option(
    "--wait-time",
    default=5,
    help="Time to wait between frames (in seconds)",
    show_default=True,
)
def main(num_frames: int, wait_time: int):
    """Live url frames grab and S3 upload function. Intended to run locally, not
    in the cloud for now."""

    for _ in range(num_frames):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        filename = f"image_{timestamp}.jpg"

        try:
            logger.info(
                f"Direct m3u8 stream extracted successfully from stream {STREAM_URL}"
            )

            direct_stream_m3u8 = get_direct_stream_url(STREAM_URL)
            frame = capture_frame_with_opencv(stream_url=direct_stream_m3u8)
            logger.info("Frame extracted successfully from m3u8 stream")

            if frame is not False:
                cv2.imwrite(TMP_OUTPUT_FILENAME, frame)

                upload_file_to_s3(
                    file_name=TMP_OUTPUT_FILENAME,
                    bucket_name=BUCKET_NAME,
                    object_name=filename,
                    region_name=REGION_NAME,
                )
                Path(TMP_OUTPUT_FILENAME).unlink()

        except Exception as e:
            logger.info(f"Error extracting frame: {e}")
            return e

        time.sleep(wait_time)


if __name__ == "__main__":
    main()
