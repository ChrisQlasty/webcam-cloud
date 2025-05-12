import logging
import os
import subprocess

logging.basicConfig(level=logging.INFO)

OUTPUT_FILENAME = "data/frame-%03d.jpg"
STREAM_URL = os.getenv("ENV_STREAM_URL")


def main():
    command = ["ffmpeg", "-y", "-i", STREAM_URL, "-vframes", "1", OUTPUT_FILENAME]

    try:
        subprocess.run(command, check=True)
        logging.info(f"Frame extracted successfully to {OUTPUT_FILENAME}")
    except subprocess.CalledProcessError as e:
        logging.info(f"Error extracting frame: {e}")


if __name__ == "__main__":
    main()
