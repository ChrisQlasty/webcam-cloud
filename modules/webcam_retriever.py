import logging
import os
import subprocess

from cloud_utils import upload_file_to_s3

logging.basicConfig(level=logging.INFO)

OUTPUT_FILENAME = "data/frame-%03d.jpg"
STREAM_URL = os.getenv("ENV_STREAM_URL")
REGION_NAME = os.getenv("ENV_REGION_NAME")


def main():
    command = ["ffmpeg", "-y", "-i", STREAM_URL, "-vframes", "1", OUTPUT_FILENAME]

    try:
        subprocess.run(command, check=True)
        logging.info(f"Frame extracted successfully to {OUTPUT_FILENAME}")

        upload_file_to_s3(
            file_name="data/frame-001.jpg",
            bucket_name="webcam-live",
            object_name="frame-001.jpg",
            region_name=REGION_NAME,
        )

    except subprocess.CalledProcessError as e:
        logging.info(f"Error extracting frame: {e}")


if __name__ == "__main__":
    main()
