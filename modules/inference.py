import io
import json
import os

from PIL import Image
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

model = None


def model_fn(model_dir: str) -> AutoDetectionModel:
    global model
    print(os.listdir(model_dir))
    print(os.path.join(model_dir, "yolo11n.pt"))
    model = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=os.path.join(model_dir, "yolo11n.pt"),
        confidence_threshold=0.6,
        device="cpu",
    )

    return model


def input_fn(request_body, content_type="application/json"):
    print("type: ", type(request_body))
    if content_type in ["application/x-image", "image/jpeg", "image/png"]:
        return Image.open(io.BytesIO(request_body))
    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(input_data, model: AutoDetectionModel):
    print("predicting...", input_data.shape)
    return get_sliced_prediction(
        input_data,
        model,
        slice_height=256,
        slice_width=256,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
    )


def output_fn(prediction, content_type="application/json"):
    print("outputting...")
    predictions_dict = prediction.to_coco_annotations()
    return json.dumps(predictions_dict)
