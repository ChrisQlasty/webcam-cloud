import os
import random

import boto3
import dash
import pandas as pd
import plotly.express as px
from dash import Input, Output, State, dcc, html

# --- AWS Configuration ---
REGION_NAME = os.getenv("TF_VAR_region", "us-east-1")  # Add a default if not set
SRC_TABLE = os.getenv(
    "TF_VAR_db_img_stats_table", "your_dynamodb_table_name"
)  # Replace with your actual table name

S3_BUCKET_NAME = "qla-processed"  # Your S3 bucket name (no s3://, no trailing /)
S3_FOLDER_PREFIX = "processed/"  # The "folder" within your S3 bucket where images are stored (e.g., "processed/")

# This image key is used as a fallback if no images are found in the bucket.
# Ensure you have a placeholder image in your 'assets' folder for errors.
S3_FALLBACK_IMAGE_PATH = "/assets/placeholder_webcam_error.png"
S3_LOADING_IMAGE_PATH = "/assets/loading_placeholder.gif"

PRESIGNED_URL_EXPIRY_SECONDS = 300  # 5 minutes for pre-signed URL expiry
S3_IMAGE_LIST_REFRESH_INTERVAL_SECONDS = 600  # Refresh S3 image list every 10 minutes

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
table = dynamodb.Table(SRC_TABLE)
s3 = boto3.client("s3", region_name=REGION_NAME)


# --- S3 Functions ---
def get_s3_presigned_url(object_key, expiry_seconds, bucket_name):
    """Generates a pre-signed URL for an S3 object."""
    # If the object_key is already an asset path (e.g., for placeholders), return it directly
    if object_key.startswith("/assets/"):
        return object_key

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiry_seconds,
        )
        # print(f"Generated pre-signed URL for {object_key}: {url[:100]}...") # Debug print
        return url
    except Exception as e:
        print(f"An error occurred generating S3 pre-signed URL for {object_key}: {e}")
        return S3_FALLBACK_IMAGE_PATH


def get_s3_image_keys_and_timestamps(bucket_name, prefix):
    """
    Lists all .jpg files in a given S3 bucket and prefix, sorted by LastModified.
    Returns a list of dictionaries: [{'key': 'obj_key', 'last_modified': datetime_obj}, ...]
    """
    image_data = []
    print(
        f"Attempting to list S3 objects in bucket: '{bucket_name}' with prefix: '{prefix}'"
    )
    try:
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

        for page in pages:
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    # Ensure it's a file (key not ending with '/') and has .jpg extension
                    if not key.endswith("/") and key.lower().endswith(".jpg"):
                        image_data.append(
                            {"key": key, "last_modified": obj["LastModified"]}
                        )
            else:
                # This message indicates that no 'Contents' section was found in a page response,
                # which is normal for an empty prefix/bucket, or if there are no matching files.
                print(
                    f"No 'Contents' found for prefix '{prefix}' or no matching files in a page."
                )

        # Sort images by their LastModified timestamp (oldest first for slider)
        image_data.sort(key=lambda x: x["last_modified"], reverse=False)

        print(f"Found {len(image_data)} .jpg images in '{bucket_name}/{prefix}'.")
        if image_data:
            print(
                f"First image: {image_data[0]['key']} ({image_data[0]['last_modified']})"
            )
            print(
                f"Last image: {image_data[-1]['key']} ({image_data[-1]['last_modified']})"
            )
        return image_data
    except boto3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "AccessDenied":
            print(
                f"AWS S3 Access Denied: Check your IAM permissions for 's3:ListBucket' on '{bucket_name}'. Error: {e}"
            )
        elif e.response["Error"]["Code"] == "NoSuchBucket":
            print(
                f"AWS S3 Error: Bucket '{bucket_name}' does not exist or you don't have access. Error: {e}"
            )
        else:
            print(f"An S3 client error occurred listing objects: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred listing S3 objects: {e}")
        return []


# --- DynamoDB Function ---
def fetch_data():
    """Fetches data from DynamoDB and returns a pandas DataFrame."""
    try:
        response = table.scan()
        items = response["Items"]
        df = pd.DataFrame(items)

        if "id" in df.columns:
            df["id"] = pd.to_datetime(
                df["id"], format="%Y-%m-%d_%H:%M:%S", errors="coerce"
            )
            df = df.dropna(subset=["id"])
            df = df.sort_values(by="id")
        return df
    except Exception as e:
        print(f"Error fetching data from DynamoDB: {e}")
        return pd.DataFrame()


# --- Dash App Initialization ---
app = dash.Dash(__name__)
app.title = "webcam-cloud dashboard"

# --- Layout Definition ---
app.layout = html.Div(
    children=[
        html.H1(
            "webcam-cloud dashboard",
            style={
                "textAlign": "center",
                "marginBottom": "30px",
                "font-family": "Roboto, sans-serif",
            },
        ),
        html.Div(
            style={"textAlign": "center", "marginBottom": "20px"},
            children=[
                html.Button(
                    "Refresh Data",
                    id="refresh-btn",
                    n_clicks=0,
                    style={
                        "padding": "10px 20px",
                        "fontSize": "16px",
                        "cursor": "pointer",
                        "marginRight": "10px",
                    },
                ),
                # Slider to select image
                html.Div(
                    style={"width": "80%", "margin": "20px auto"},
                    children=[
                        html.Label("Select Image:"),  # More generic label
                        dcc.Slider(
                            id="image-slider",
                            min=0,
                            max=0,
                            value=0,
                            marks={},  # Empty marks initially, populated by callback
                            step=1,  # <--- FIXED: Set step to 1
                            disabled=True,  # Disable until images are loaded
                            tooltip={
                                "placement": "bottom",
                                "always_visible": True,
                                "style": {"font-size": "12px"},
                            },
                        ),
                    ],
                ),
            ],
        ),
        # This is the main grid container
        html.Div(
            style={
                "display": "grid",
                "grid-template-columns": "1fr 1fr",
                "grid-template-rows": "1fr 1fr",
                "gap": "20px",
                "height": "80vh",
                "width": "90vw",
                "margin": "auto",
                "padding": "15px",
                "border": "1px solid #ddd",
                "borderRadius": "8px",
                "boxShadow": "2px 2px 10px rgba(0,0,0,0.1)",
            },
            children=[
                # Top-Left Cell: Image (Webcam Feed)
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "display": "flex",
                        "flexDirection": "column",  # Arrange children vertically
                        "justifyContent": "flex-start",  # Align items to the top to give title space
                        "alignItems": "center",
                        "overflow": "hidden",
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                        "padding": "10px",  # Add some padding inside the cell
                    },
                    children=[
                        html.Div(
                            id="webcam-image-title",
                            children="Loading Image...",  # Initial title
                            style={
                                "fontWeight": "bold",
                                "marginBottom": "5px",  # <--- FIXED: Reduced margin
                                "fontSize": "1em",  # <--- FIXED: Slightly smaller font
                                "textAlign": "center",
                                "width": "100%",  # Ensure it takes full width for wrapping
                                "wordWrap": "break-word",  # Ensure long words break
                            },
                        ),
                        html.Img(
                            src=S3_LOADING_IMAGE_PATH,
                            id="webcam-feed",
                            alt="Webcam Feed",
                            style={
                                "maxWidth": "100%",
                                "maxHeight": "calc(100% - 30px)",  # <--- FIXED: Calc to leave space for title + buffer
                                "objectFit": "contain",
                                "flexGrow": 0,  # Don't grow indefinitely, respect maxHeight
                                "flexShrink": 1,  # Allow shrinking if necessary
                            },
                        ),
                    ],
                ),
                # Top-Right Cell: Chart 1 (Category Counts)
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                    },
                    children=[
                        dcc.Graph(
                            id="cat_count_graph",
                            style={"height": "100%", "width": "100%"},
                        )
                    ],
                ),
                # Bottom-Left Cell: Chart 2 (Dummy chart)
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                    },
                    children=[
                        dcc.Graph(
                            id="chart-2", style={"height": "100%", "width": "100%"}
                        )
                    ],
                ),
                # Bottom-Right Cell: Chart 3 (Dummy chart)
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                    },
                    children=[
                        dcc.Graph(
                            id="chart-3", style={"height": "100%", "width": "100%"}
                        )
                    ],
                ),
            ],
        ),
        # Store for image metadata (keys and timestamps)
        dcc.Store(id="image-keys-store", data=[]),
        # Interval components for refreshing
        dcc.Interval(
            id="image-url-refresh-interval",  # Refreshes the CURRENT image URL periodically
            interval=(PRESIGNED_URL_EXPIRY_SECONDS - 30)
            * 1000,  # Refresh 30s before expiry
            n_intervals=0,
        ),
        dcc.Interval(
            id="image-list-update-interval",  # Refreshes the LIST of S3 images (and slider)
            interval=S3_IMAGE_LIST_REFRESH_INTERVAL_SECONDS * 1000,
            n_intervals=0,
        ),
    ],
    style={
        "backgroundColor": "#e6e5e5cc",
    },
)

# --- Callbacks ---


# Callback to update the S3 image list and slider properties
@app.callback(
    Output("image-keys-store", "data"),
    Output("image-slider", "min"),
    Output("image-slider", "max"),
    Output("image-slider", "value"),
    Output("image-slider", "marks"),
    Output("image-slider", "disabled"),
    Input("image-list-update-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),  # Also refresh list on manual refresh
)
def update_image_list_and_slider(n_intervals_list, n_clicks_refresh):
    print(
        f"Triggered: update_image_list_and_slider (interval={n_intervals_list}, refresh_btn={n_clicks_refresh})"
    )
    image_data = get_s3_image_keys_and_timestamps(S3_BUCKET_NAME, S3_FOLDER_PREFIX)

    if not image_data:
        print("No images found in S3 bucket/prefix. Slider disabled.")
        return (
            [],
            0,
            0,
            0,
            {0: {"label": "No images found", "style": {"color": "#f50"}}},
            True,
        )

    marks = {}
    num_images = len(image_data)
    # Define how many marks you want to show for large sets (e.g., max 10-20 visible marks)
    desired_mark_count = min(num_images, 20)  # Show all if <=20, otherwise max 20
    if desired_mark_count > 0:
        step_for_marks = max(1, num_images // desired_mark_count)
        for i in range(num_images):
            if (
                i % step_for_marks == 0 or i == num_images - 1
            ):  # Always include first and last
                marks[i] = {"label": ""}  # <--- FIXED: Empty label for marks
    else:  # Case for num_images = 0 (though already handled above)
        marks[0] = {"label": ""}

    # Default to the latest image (last element in sorted list)
    latest_image_index = len(image_data) - 1

    return image_data, 0, latest_image_index, latest_image_index, marks, False


# Callback to update the displayed image and its title based on slider value
@app.callback(
    Output("webcam-feed", "src"),
    Output("webcam-image-title", "children"),  # New output for the image title
    Input("image-slider", "drag_value"),
    Input(
        "image-url-refresh-interval", "n_intervals"
    ),  # To refresh URL for currently selected image
    State("image-keys-store", "data"),  # Get the full image list from the store
    State("image-slider", "value"),
)
def update_webcam_feed(
    drag_value, n_intervals_url, image_keys_data, current_slider_value
):
    print(
        f"Triggered: update_webcam_feed (drag_value={drag_value}, url_refresh={n_intervals_url})"
    )

    if not image_keys_data:
        print("Image keys data is empty. Displaying error placeholder.")
        return S3_FALLBACK_IMAGE_PATH, "No Images Found"

    # Use drag_value if available and not None, otherwise fall back to current_slider_value
    # drag_value can be None on initial load until the slider is interacted with
    effective_slider_value = (
        drag_value if drag_value is not None else current_slider_value
    )

    # Ensure effective_slider_value is within valid range
    if effective_slider_value is None or not (
        0 <= effective_slider_value < len(image_keys_data)
    ):
        print(
            f"Invalid slider value {effective_slider_value}. Falling back to latest image."
        )
        selected_image_info = image_keys_data[-1]
    else:
        selected_image_info = image_keys_data[effective_slider_value]

    selected_image_key = selected_image_info["key"]
    image_timestamp = selected_image_info["key"].split("image_")[-1].split(".jpg")[0]

    # Format timestamp for display
    title_text = f"Image taken: {image_timestamp} "  # .strftime('%Y-%m-%d %H:%M:%S')}"

    # Generate pre-signed URL
    image_src = get_s3_presigned_url(
        selected_image_key, PRESIGNED_URL_EXPIRY_SECONDS, S3_BUCKET_NAME
    )

    return image_src, title_text


# Callback for charts (combined into one for efficiency)
@app.callback(
    Output("cat_count_graph", "figure"),
    Output("chart-2", "figure"),
    Output("chart-3", "figure"),
    Input("image-slider", "drag_value"),
    Input("refresh-btn", "n_clicks"),
    Input(
        "image-url-refresh-interval", "n_intervals"
    ),  # Use the same interval that refreshes image URL
)
def update_graphs(n_clicks_refresh, n_intervals_url, drag_value):
    print(
        f"Triggered: update_graphs (refresh_btn={n_clicks_refresh}, interval={n_intervals_url})"
    )
    df = fetch_data()
    update_trigger_count = n_clicks_refresh + n_intervals_url

    # Cat Count Graph
    if df.empty:
        fig_cat_count = px.scatter(title="No Data Available for Category Counts")
    else:
        df_filtered = df[df["category_name"] != "whole_image"]
        df_filtered["count"] = pd.to_numeric(df_filtered["count"], errors="coerce")
        fig_cat_count = px.line(
            df_filtered,
            x="id",
            y="count",
            color="category_name",
            markers=True,
            title="Category Counts Over Time",
        )
        fig_cat_count.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5
        )

    # Dummy data for Chart 2 & 3
    df_dummy = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5],
            "y1": [random.randint(10, 50) for _ in range(5)],
            "y2": [random.randint(20, 60) for _ in range(5)],
            "y3": [random.randint(5, 40) for _ in range(5)],
        }
    )
    fig_chart2 = px.line(
        df_dummy,
        x="x",
        y="y2",
        title=f"Sensor Readings (Updates: {update_trigger_count})",
    )
    fig_chart3 = px.scatter(
        df_dummy, x="x", y="y3", title=f"Event Counts (Updates: {update_trigger_count})"
    )

    fig_chart2.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5)
    fig_chart3.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5)

    return fig_cat_count, fig_chart2, fig_chart3


if __name__ == "__main__":
    app.run(debug=True)
