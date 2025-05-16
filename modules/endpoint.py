# Inference code from tutorial [YOLO11 + SAHI walkthrough] from https://github.com/obss/sahi?tab=readme-ov-file#tutorials

import pandas as pd
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction


def main():
    detection_model = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path="yolo11n.pt",
        confidence_threshold=0.35,
        device="cpu",
    )

    result = get_sliced_prediction(
        "data/output.jpg",
        detection_model,
        slice_height=256,
        slice_width=256,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
    )
    predictions_dict = result.to_coco_annotations()
    predictions_df = pd.DataFrame(predictions_dict)
    print(predictions_df)


if __name__ == "__main__":
    main()
