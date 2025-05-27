import io
import json
import logging
import os

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from sahi.prediction import PredictionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model = None


def model_fn(model_dir: str) -> AutoDetectionModel:
    global model

    logger.info("model_fn")
    logger.info(f"Files in {model_dir}: {os.listdir(model_dir)}")

    path = os.path.join(model_dir, "yolo11n.pt")

    logger.info(f"Looking for model at: {path}")
    model = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=os.path.join(model_dir, "yolo11n.pt"),
        confidence_threshold=0.6,
        device="cpu",
    )

    return model


def input_fn(request_body: bytes, content_type: str = "application/json") -> NDArray:
    logger.info("input_fn")
    if content_type in ["application/x-image", "image/jpeg", "image/png"]:
        pil_image = Image.open(io.BytesIO(request_body))
        return np.array(pil_image)
    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(input_data: NDArray, model: AutoDetectionModel) -> PredictionResult:
    logger.info("predict_fn")
    return get_sliced_prediction(
        input_data,
        model,
        slice_height=256,
        slice_width=256,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
    )


def output_fn(prediction: PredictionResult, content_type="application/json") -> bytes:
    logger.info("output_fn")
    predictions_dict = prediction.to_coco_annotations()
    return json.dumps(predictions_dict)
