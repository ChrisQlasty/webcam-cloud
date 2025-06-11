import base64
import io
import os

import boto3
import dash
import pandas as pd
import plotly.colors
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from PIL import Image

from utils.aws_cloud import load_jpeg_from_s3, load_json_from_s3

# --- AWS Configuration ---
REGION_NAME = os.getenv("TF_VAR_region", "us-east-1")
SRC_TABLE = os.getenv("TF_VAR_db_img_stats_table", "your_dynamodb_table_name")
S3_BUCKET_NAME = os.getenv("TF_VAR_processed_bucket")
DEBUG = os.getenv("DASH_debug", "false").lower() in ("true", "1", "t")

S3_FOLDER_PREFIX = "processed/"

# This image key is used as a fallback if no images are found in the bucket.
# Ensure you have a placeholder image in your 'assets' folder for errors.
S3_FALLBACK_IMAGE_PATH = "/assets/placeholder_webcam_error.png"
S3_LOADING_IMAGE_PATH = "/assets/loading_placeholder.gif"

REFRESH_SECONDS = 300  # 5 minutes for pre-signed URL expiry
S3_IMAGE_LIST_REFRESH_INTERVAL_SECONDS = 600  # Refresh S3 image list every 10 minutes

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
table = dynamodb.Table(SRC_TABLE)
s3 = boto3.client("s3", region_name=REGION_NAME)


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
            # Add a print statement for the full error response for debugging
            print(f"Full error response: {e.response}")
        else:
            print(f"An S3 client error occurred listing objects: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred listing S3 objects: {e}")
        return []


# --- DynamoDB Function ---
def fetch_data():
    """Fetches data from DynamoDB and returns a pandas DataFrame and distinct category names."""
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

        # Convert numeric columns that might be stored as Decimal or strings
        numeric_cols = ["count", "mean_area", "mean_score", "mean_brightness"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Extract distinct category names (excluding 'whole_image')
        distinct_categories = (
            df["category_name"].dropna().unique().tolist()
            if "category_name" in df.columns
            else []
        )
        distinct_categories = [
            cat for cat in distinct_categories if cat != "whole_image"
        ]

        return df, distinct_categories
    except Exception as e:
        print(f"Error fetching data from DynamoDB: {e}")
        return pd.DataFrame(), []


# --- Dash App Initialization ---
app = dash.Dash(__name__)
app.title = "webcam-cloud dashboard"
server = app.server

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
                            step=1,
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
                                "marginBottom": "5px",
                                "fontSize": "1em",
                                "textAlign": "center",
                                "width": "100%",
                                "wordWrap": "break-word",
                            },
                        ),
                        # Use dcc.Graph instead of html.Img
                        dcc.Graph(
                            id="webcam-graph",
                            figure={},  # Initial empty figure
                            config={
                                "displayModeBar": False,  # Hide modebar
                                "scrollZoom": True,  # Allow zooming
                            },
                            style={
                                "maxWidth": "100%",
                                "maxHeight": "calc(100% - 30px)",
                                # objectFit: 'contain' is handled by layout settings in the figure
                                "flexGrow": 0,
                                "flexShrink": 1,
                            },
                        ),
                    ],
                ),
                # Top-Right Cell: New Scatter Plot
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
                # Bottom-Left Cell: Chart 1 (Category Counts)
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
                # Bottom-Right Cell: Mean Brightness Chart
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                    },
                    children=[
                        dcc.Graph(
                            id="mean_brightness_graph",
                            style={"height": "100%", "width": "100%"},
                        )
                    ],
                ),
            ],
        ),
        # Store for image metadata (keys and timestamps)
        dcc.Store(id="image-keys-store", data=[]),
        # Store for bounding box data of the currently displayed image
        dcc.Store(id="bbox-data-store", data={}),
        # Interval components for refreshing
        dcc.Interval(
            id="image-url-refresh-interval",  # Refreshes the CURRENT image URL periodically
            interval=(REFRESH_SECONDS - 30) * 1000,  # Refresh 30s before expiry
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


# --- Generate a color mapping for categories ---
def generate_color_mapping(categories):
    color_palette = (
        plotly.colors.qualitative.Set1
    )  # Use a predefined Plotly color palette
    color_mapping = {
        category: color_palette[i % len(color_palette)]
        for i, category in enumerate(categories)
    }
    return color_mapping


# --- Callbacks ---


# Callback to update the S3 image list and slider properties
@callback(
    Output("image-keys-store", "data"),
    Output("image-slider", "min"),
    Output("image-slider", "max"),
    Output("image-slider", "value"),
    Output("image-slider", "marks"),
    Output("image-slider", "disabled"),
    Input("image-list-update-interval", "n_intervals"),
)
def update_image_list_and_slider(n_intervals_list):
    print(f"Triggered: update_image_list_and_slider (interval={n_intervals_list})")
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
        indices_to_mark = list(range(0, num_images, step_for_marks))
        if (num_images - 1) not in indices_to_mark:
            indices_to_mark.append(num_images - 1)

        for i in indices_to_mark:
            marks[i] = {"label": ""}  # Empty label for marks

    else:  # Case for num_images = 0 (though already handled above)
        marks[0] = {"label": ""}

    # Default to the latest image (last element in sorted list)
    latest_image_index = len(image_data) - 1

    return image_data, 0, latest_image_index, latest_image_index, marks, False


# Callback to update the displayed image, its title, and store bbox data
@callback(
    Output("webcam-graph", "figure"),  # Outputting the figure for the graph
    Output("webcam-image-title", "children"),
    Output("bbox-data-store", "data"),  # Outputting bbox data to store
    Input("image-slider", "drag_value"),
    Input("image-url-refresh-interval", "n_intervals"),
    State("image-keys-store", "data"),
    State("image-slider", "value"),
)
def update_webcam_graph_and_data(
    drag_value, n_intervals_url, image_keys_data, current_slider_value
):
    print(
        f"Triggered: update_webcam_graph_and_data (drag_value={drag_value}, url_refresh={n_intervals_url})"
    )

    if not image_keys_data:
        print("Image keys data is empty. Displaying error placeholder.")
        # Return a figure with the fallback image
        fig = go.Figure()
        fig.add_layout_image(
            dict(
                source=S3_FALLBACK_IMAGE_PATH,
                xref="paper",
                yref="paper",
                x=0,
                y=1,
                sizex=1,
                sizey=1,
                sizing="stretch",
                opacity=1,
                layer="below",
            )
        )
        fig.update_layout(
            xaxis=dict(visible=False, range=[0, 1]),
            yaxis=dict(visible=False, range=[0, 1]),
            margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="rgba(0,0,0,0)",  # Make background transparent
            uirevision="Don't reset on callback",  # Keep zoom/pan
        )
        return fig, "No Images Found", {}  # Return empty bbox data

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

    title_text = f"Image taken: {image_timestamp} "

    # load image from S3
    image_np = load_jpeg_from_s3(s3, S3_BUCKET_NAME, selected_image_key)
    img_height, img_width = image_np.shape[:-1]
    image_pil = Image.fromarray(image_np)
    buffered = io.BytesIO()
    image_pil.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    image_src = f"data:image/png;base64,{img_str}"

    # --- Fetch Bounding Box Data from S3 JSON ---
    json_key = selected_image_key + ".out"
    bbox_data_raw = []

    try:
        # Fetch JSON data
        bbox_data_raw = load_json_from_s3(s3, S3_BUCKET_NAME, json_key)
        if bbox_data_raw is None:  # load_json_from_s3 returns None on error
            bbox_data_raw = []
            print(f"Could not load bbox data from {json_key}")

    except Exception as e:
        print(
            f"Error fetching bbox data or image dimensions for {selected_image_key}: {e}"
        )
        bbox_data_raw = []  # Ensure empty list on error
        img_width = None
        img_height = None

    # Create the figure with the image
    fig = go.Figure()
    fig.add_layout_image(
        dict(
            source=image_src,
            xref="paper",
            yref="paper",
            x=0,
            y=1,
            sizex=1,
            sizey=1,
            sizing="stretch",
            opacity=1,
            layer="below",
        )
    )

    # Generate color mapping
    _, distinct_categories = fetch_data()
    color_mapping = generate_color_mapping(distinct_categories)

    # Add shapes (bounding boxes) with consistent colors
    shapes = []
    if bbox_data_raw and img_width is not None and img_height is not None:
        for box_info in bbox_data_raw:
            # bbox is [x, y, width, height] in pixel coordinates (y=0 top)
            x, y, w, h = box_info["bbox"]
            label = box_info.get("category_name", "unknown")
            color = color_mapping.get(label, "red")  # Default to red if label not found

            # Convert pixel coordinates [x, y, w, h] to relative [x0, y0, x1, y1] (y=0 top)
            x0_rel = x / img_width
            y0_rel = y / img_height
            x1_rel = (x + w) / img_width
            y1_rel = (y + h) / img_height

            # Convert relative [x0, y0, x1, y1] (y=0 top) to Plotly's relative [x0, y0, x1, y1] (y=0 bottom)
            x0_plotly = x0_rel
            y0_plotly = 1 - y1_rel  # Plotly y0 is bottom edge
            x1_plotly = x1_rel
            y1_plotly = 1 - y0_rel  # Plotly y1 is top edge
            shapes.append(
                dict(
                    type="rect",
                    xref="paper",
                    yref="paper",
                    x0=x0_plotly,
                    y0=y0_plotly,
                    x1=x1_plotly,
                    y1=y1_plotly,
                    line=dict(color=color, width=3),
                    opacity=0.7,
                )
            )
            fig.add_annotation(
                x=x0_plotly,
                y=y1_plotly,
                xref="paper",
                yref="paper",
                text=label,
                showarrow=False,
                align="left",
            )

    fig.update_layout(
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[0, 1]),
        margin=dict(l=0, r=0, t=0, b=0),
        shapes=shapes,
        plot_bgcolor="rgba(0,0,0,0)",
        uirevision=selected_image_key,  # Use image key to preserve zoom/pan when image changes
    )

    # Store the raw bbox data and image dimensions
    bbox_store_data = {
        "bboxes": bbox_data_raw,
        "img_width": img_width,
        "img_height": img_height,
    }

    return fig, title_text, bbox_store_data


# Callback for charts (combined into one for efficiency)
@callback(
    Output("cat_count_graph", "figure"),
    Output("chart-2", "figure"),
    Output("mean_brightness_graph", "figure"),
    Input("image-slider", "drag_value"),
    Input("image-url-refresh-interval", "n_intervals"),
    State("image-keys-store", "data"),
    State("image-slider", "value"),
)
def update_graphs(drag_value, n_intervals_url, image_keys_data, current_slider_value):
    print(
        f"Triggered: update_graphs (drag_value={drag_value}, interval={n_intervals_url})"
    )
    df, distinct_categories = fetch_data()
    color_mapping = generate_color_mapping(distinct_categories)

    # --- Determine Selected Timestamp for filtering ---
    selected_timestamp_dt = None
    selected_timestamp_str = "N/A"
    if image_keys_data:
        effective_slider_value = (
            drag_value if drag_value is not None else current_slider_value
        )
        if 0 <= effective_slider_value < len(image_keys_data):
            selected_image_info = image_keys_data[effective_slider_value]
            timestamp_str_from_key = (
                selected_image_info["key"].split("image_")[-1].split(".jpg")[0]
            )
            try:
                selected_timestamp_dt = pd.to_datetime(
                    timestamp_str_from_key, format="%Y-%m-%d_%H:%M:%S"
                )
                selected_timestamp_str = selected_timestamp_dt.strftime(
                    "%Y-%m-%d_%H:%M:%S"
                )
            except ValueError:
                print(
                    f"Could not parse timestamp from key: {selected_image_info['key']}"
                )
        elif (
            image_keys_data
        ):  # If invalid slider value, default to latest for timestamp string
            latest_image_key = image_keys_data[-1]["key"]
            selected_timestamp_str = latest_image_key.split("image_")[-1].split(".jpg")[
                0
            ]
            try:
                selected_timestamp_dt = pd.to_datetime(
                    selected_timestamp_str, format="%Y-%m-%d_%H:%M:%S"
                )
            except ValueError:
                pass  # Already handled, or will be caught by df.empty check

    # Cat Count Graph (Bottom-Left)
    if df.empty:
        fig_cat_count = px.scatter(title="No Data Available for Category Counts")
    else:
        df_filtered = df[df["category_name"] != "whole_image"].copy()
        df_filtered["count"] = pd.to_numeric(df_filtered["count"], errors="coerce")
        df_filtered = df_filtered.sort_values(by=["category_name", "id"])
        fig_cat_count = px.line(
            df_filtered,
            x="id",
            y="count",
            color="category_name",
            color_discrete_map=color_mapping,
            markers=True,
            title="Category Counts Over Time",
        )
        fig_cat_count.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5
        )

    # New Scatter Plot (Top-Right, formerly chart-2)
    fig_new_scatter = px.scatter(title="No Data for Object Properties")
    if not df.empty and selected_timestamp_dt:
        # Filter df for the selected timestamp AND exclude 'whole_image' category
        df_scatter_data = df[
            (df["id"] == selected_timestamp_dt) & (df["category_name"] != "whole_image")
        ].copy()

        if not df_scatter_data.empty:
            # Ensure numeric types
            df_scatter_data["mean_area"] = pd.to_numeric(
                df_scatter_data["mean_area"], errors="coerce"
            )
            df_scatter_data["count"] = pd.to_numeric(
                df_scatter_data["count"], errors="coerce"
            )
            df_scatter_data["mean_score"] = pd.to_numeric(
                df_scatter_data["mean_score"], errors="coerce"
            )

            # Remove rows with NaN in relevant columns if they are critical for plotting
            df_scatter_data.dropna(
                subset=["mean_area", "count", "mean_score"], inplace=True
            )
            df_scatter_data = df_scatter_data.sort_values(by="category_name")

            if not df_scatter_data.empty:
                fig_new_scatter = px.scatter(
                    df_scatter_data,
                    x="mean_area",
                    y="count",
                    size="mean_score",
                    color="category_name",  # Color by category for better insights
                    color_discrete_map=color_mapping,
                    hover_name="category_name",
                    title=f"Objects: Area, Count, Score for {selected_timestamp_str}",
                )
                fig_new_scatter.update_layout(
                    margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5
                )
            else:
                fig_new_scatter = px.scatter(
                    title=f"No valid object data for {selected_timestamp_str}"
                )
        else:
            fig_new_scatter = px.scatter(
                title=f"No object detection data for {selected_timestamp_str}"
            )
    elif not df.empty:
        fig_new_scatter = px.scatter(title="Select an image to view object properties")

    # Mean Brightness Graph
    if df.empty:
        fig_mean_brightness = px.scatter(title="No Data Available for Mean Brightness")
    else:
        # Assuming mean_brightness is associated with 'whole_image' category
        df_brightness = df[df["category_name"] == "whole_image"].copy()
        if not df_brightness.empty:
            df_brightness["mean_brightness"] = pd.to_numeric(
                df_brightness["mean_brightness"], errors="coerce"
            )
            fig_mean_brightness = px.line(
                df_brightness,
                x="id",
                y="mean_brightness",
                title="Mean Brightness Over Time",
                markers=True,
            )
            fig_mean_brightness.update_layout(
                margin={"r": 0, "t": 40, "l": 0, "b": 0}, title_x=0.5
            )
        else:
            fig_mean_brightness = px.scatter(
                title="No 'whole_image' data for Mean Brightness"
            )

    return fig_cat_count, fig_new_scatter, fig_mean_brightness


if __name__ == "__main__":
    app.run(debug=DEBUG)
