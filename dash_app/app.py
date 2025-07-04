import base64
import io
import logging
import os
from datetime import datetime

import boto3
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dash_table, dcc, html
from dash_bootstrap_templates import load_figure_template
from PIL import Image

from dash_app.dash_utils import (
    compare_timezones,
    extract_timestamp_from_key,
    generate_color_mapping,
    get_theme_name,
)
from modules.constants import ALLOWED_CATEGORIES, PROCESSED_FOLDER, YT_METADATA_FILE
from utils.aws_cloud import (
    get_s3_image_keys_and_timestamps,
    load_jpeg_from_s3,
    load_json_from_s3,
)

# --- CONSTANTS & ENV VARS ---
STREAM_URL = os.getenv("ENV_STREAM_URL")
REGION_NAME = os.getenv("TF_VAR_region")
SRC_TABLE = os.getenv("TF_VAR_db_img_stats_table")
S3_BUCKET_NAME = os.getenv("TF_VAR_processed_bucket")

DEBUG = os.getenv("DASH_debug", "false").lower() in ("true", "1", "t")

S3_FOLDER_PREFIX = f"{PROCESSED_FOLDER}/"
S3_FALLBACK_IMAGE_PATH = "/assets/placeholder_webcam_error.png"
S3_LOADING_IMAGE_PATH = "/assets/loading_placeholder.gif"

REFRESH_SECONDS = 300
S3_IMAGE_LIST_REFRESH_INTERVAL_SECONDS = 600  # Refresh S3 image list every 10 minutes
DBC_TEMPLATE = dbc.themes.SUPERHERO

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
table = dynamodb.Table(SRC_TABLE)
s3 = boto3.client("s3", region_name=REGION_NAME)

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Extraction of YT live stream info & timezone comparison
load_figure_template(get_theme_name(DBC_TEMPLATE).lower())
META = load_json_from_s3(s3, S3_BUCKET_NAME, YT_METADATA_FILE)
YT_TITLE, YT_DESCRIPTION = META["title"], META["description"]
TIME_DIFF = compare_timezones(query_city=YT_TITLE.replace("Live", ""))


# --- GLOBAL CACHES ---
IMAGE_KEYS_CACHE = []
BBOX_JSONS_CACHE = {}


def load_all_images_and_jsons():
    """Loads all image keys and their corresponding bbox JSONs from S3 into memory."""
    global IMAGE_KEYS_CACHE, BBOX_JSONS_CACHE
    IMAGE_KEYS_CACHE = get_s3_image_keys_and_timestamps(
        S3_BUCKET_NAME, S3_FOLDER_PREFIX
    )
    BBOX_JSONS_CACHE = {}
    for item in IMAGE_KEYS_CACHE:
        key = item["key"]
        json_key = key + ".out"
        try:
            bbox_data = load_json_from_s3(s3, S3_BUCKET_NAME, json_key)
            if bbox_data is None:
                bbox_data = []
        except Exception as e:
            logger.info(f"Error loading bbox JSON for {json_key}: {e}")
            bbox_data = []
        BBOX_JSONS_CACHE[key] = bbox_data


# --- INITIAL LOAD ---
load_all_images_and_jsons()


# --- DynamoDB Function ---
def fetch_data():
    """Fetches data from DynamoDB and returns a pandas DataFrame and distinct category names."""
    try:
        response = table.scan()
        items = response["Items"]
        df = pd.DataFrame(items)

        if "id" in df.columns:
            df.rename(columns={"id": "timestamp"}, inplace=True)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], format="%Y-%m-%d_%H:%M:%S", errors="coerce"
            )
            df["timestamp"] = df["timestamp"] + pd.Timedelta(hours=TIME_DIFF)
            df = df.dropna(subset=["timestamp"])
            df = df.sort_values(by="timestamp")

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

        # --- Fill missing categories with count=0 for each timestamp ---
        if not df.empty and "timestamp" in df.columns and "category_name" in df.columns:
            # Get all timestamps from 'whole_image' rows (these are the reference timestamps)
            all_timestamps = df[df["category_name"] == "whole_image"][
                "timestamp"
            ].unique()
            # Build a MultiIndex of all (timestamp, category) pairs (excluding 'whole_image')
            full_index = pd.MultiIndex.from_product(
                [all_timestamps, distinct_categories],
                names=["timestamp", "category_name"],
            )
            # Filter out only non-'whole_image' rows
            df_non_whole = df[df["category_name"] != "whole_image"].copy()
            df_non_whole = df_non_whole.set_index(["timestamp", "category_name"])
            # Reindex to fill missing (timestamp, category) pairs with NaN
            df_filled = df_non_whole.reindex(full_index)
            # Fill missing 'count' with 0, keep other columns as NaN
            df_filled["count"] = df_filled["count"].fillna(0)
            # Reset index for downstream compatibility
            df_filled = df_filled.reset_index()
            # Concatenate back the 'whole_image' rows
            df_whole = df[df["category_name"] == "whole_image"].copy()
            df = pd.concat([df_filled, df_whole], ignore_index=True, sort=False)
            df = df.sort_values(by=["timestamp", "category_name"])

        return df, distinct_categories
    except Exception as e:
        logger.info(f"Error fetching data from DynamoDB: {e}")
        return pd.DataFrame(), []


# --- Dash App Initialization ---
app = dash.Dash(__name__, external_stylesheets=[DBC_TEMPLATE], assets_folder="assets")
app.title = "webcam-cloud dashboard"
server = app.server

# --- Layout Definition ---
app.layout = html.Div(
    style={
        "display": "grid",
        "gridTemplateColumns": "300px 1fr",  # Narrow left, wide right
        "height": "100vh",
        "width": "100vw",
        "gap": "0",
    },
    children=[
        # Area 1: Left column
        html.Div(
            style={
                "display": "flex",
                "flexDirection": "column",
                "alignItems": "center",
                "padding": "30px 10px 10px 10px",
                "height": "100vh",
                "boxShadow": "2px 0 8px rgba(0,0,0,0.07)",
            },
            children=[
                html.H1(
                    "webcam-cloud dashboard",
                    style={
                        "textAlign": "center",
                        "marginBottom": "40px",
                    },
                ),
                # Add the YouTube stream button here
                dbc.Button(
                    "Visit YouTube stream",
                    href=STREAM_URL,  # <-- Paste your URL here
                    external_link=True,  # Opens in a new tab
                    color="primary",  # Use a primary color from the theme
                    className="mb-4",  # Add margin-bottom using Bootstrap class
                    style={"width": "90%"},  # Make button fill container width
                    target="_blank",  # Open in new tab
                ),
                # Text fields for title and description
                html.H5(
                    YT_TITLE if YT_TITLE else "Stream Title Not Available",
                    style={
                        "textAlign": "center",
                        "marginBottom": "10px",
                    },
                ),
                html.P(
                    YT_DESCRIPTION if YT_DESCRIPTION else "Description Not Available",
                    style={
                        "textAlign": "justify",
                        "fontSize": "0.9rem",
                        "marginBottom": "20px",
                        "color": "#C4C4C4",
                    },
                ),
                html.Label(
                    "Select Image:",
                    style={
                        "color": "#fff",
                        "marginBottom": "10px",
                        "marginTop": "20px",
                        "fontWeight": "bold",
                    },
                ),
                dash_table.DataTable(
                    id="image-table",
                    columns=[
                        {"name": "Timestamp", "id": "timestamp"}
                    ],  # Define columns
                    data=[],  # Initial empty data
                    row_selectable="single",  # Allow selecting one row
                    selected_rows=[0],  # Select the first row by default
                    style_table={
                        "overflowY": "auto",
                        "height": "calc(100vh - 550px)",
                    },  # Set table height and enable scrolling
                    style_cell={
                        "textAlign": "left",
                        "minWidth": "100px",
                        "width": "150px",
                        "maxWidth": "200px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                        "backgroundColor": "#1e1e1e",  # Match sidebar background
                        "color": "#fff",  # White text
                        "border": "1px solid #333",  # Darker border
                    },
                    style_header={
                        # "backgroundColor": "#2a2a2a",  # Darker header background
                        "color": "#fff",
                        "fontWeight": "bold",
                        "border": "1px solid #333",
                    },
                    style_data_conditional=[
                        {
                            "if": {"row_index": "odd"},
                            # "backgroundColor": "#282828",  # Slightly different background for odd rows
                        },
                        {
                            "if": {"state": "selected"},  # Style for selected row
                            "backgroundColor": "#0074D9",
                            "border": "1px solid #0074d9",
                            "color": "#fff",  # Ensure text is white on highlight
                        },
                    ],
                    sort_action="native",  # Enable sorting
                    sort_mode="single",  # Allow sorting by a single column
                    sort_by=[
                        {"column_id": "timestamp", "direction": "desc"}
                    ],  # Sort by timestamp descending by default
                ),
                html.Div(
                    style={
                        "marginTop": "20px",  # Add space above the links
                        "textAlign": "center",  # Center the links
                        "width": "100%",  # Ensure the div takes full width
                    },
                    children=[
                        html.A(
                            html.Img(
                                src="/assets/github-icon.png",
                                style={
                                    "height": "30px",
                                    "verticalAlign": "middle",
                                },  # Style the icon size and alignment
                            ),
                            href="https://github.com/ChrisQlasty/webcam-cloud",
                            target="_blank",  # Open in new tab
                            style={
                                "color": "#fff",
                                "marginRight": "15px",
                            },  # Style color
                        ),
                        html.A(
                            html.Img(
                                src="/assets/dash-icon.png",
                                style={
                                    "height": "30px",
                                    "verticalAlign": "middle",
                                    "marginRight": "5px",
                                },  # Style the icon size and alignment
                            ),
                            href="https://dash.plotly.com/",
                            target="_blank",  # Open in new tab
                            style={
                                "color": "#fff",
                            },  # Add space between links and style color
                        ),
                    ],
                ),
            ],
        ),
        # Area 2: Right column (2x2 grid for figures)
        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gridTemplateRows": "1fr 1fr",
                "height": "100vh",
                "width": "100%",
                "boxSizing": "border-box",
                "background": "#222",
            },
            children=[
                html.Div(
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "height": "100%",
                        "width": "100%",
                        "overflow": "hidden",
                    },
                    children=[
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
                                "maxHeight": "100%",
                                "height": "100%",
                                "width": "100%",
                                "flex": "1 1 auto",
                            },
                        ),
                    ],
                ),
                # Top-Right Cell: New Scatter Plot
                html.Div(
                    children=[
                        dcc.Graph(
                            id="chart-2", style={"height": "100%", "width": "100%"}
                        )
                    ],
                ),
                # Bottom-Left Cell: Chart 1 (Category Counts)
                html.Div(
                    children=[
                        dcc.Graph(
                            id="cat_count_graph",
                            style={"height": "100%", "width": "100%"},
                        )
                    ],
                ),
                # Bottom-Right Cell: Mean Brightness Chart
                html.Div(
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
)


# --- Callbacks ---


@callback(
    Output("image-keys-store", "data"),
    Output("image-table", "data"),
    Output("image-table", "columns"),
    Output("image-table", "selected_rows"),
    Input("image-list-update-interval", "n_intervals"),
)
def update_image_list_and_table(n_intervals_list):
    logger.info(f"Triggered: update_image_list_and_table (interval={n_intervals_list})")
    # Refresh cache
    load_all_images_and_jsons()
    image_data = IMAGE_KEYS_CACHE

    if not image_data:
        logger.info("No images found in S3 bucket/prefix. Table disabled.")
        return (
            [],
            [{"timestamp": "No images found"}],
            [{"name": "Timestamp", "id": "timestamp"}],
            [],
        )

    image_data.sort(key=lambda x: extract_timestamp_from_key(x["key"]), reverse=True)
    table_data = []
    for item in image_data:
        timestamp_dt = extract_timestamp_from_key(item["key"])
        timestamp_dt = timestamp_dt + pd.Timedelta(hours=TIME_DIFF)
        timestamp_str = (
            timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")
            if timestamp_dt != datetime.min
            else "Invalid Timestamp"
        )
        table_data.append({"timestamp": timestamp_str})

    table_columns = [{"name": "Timestamp", "id": "timestamp"}]
    selected_rows = [0] if table_data else []

    return image_data, table_data, table_columns, selected_rows


# Callback to update the displayed image, its title, and store bbox data
@callback(
    Output("webcam-graph", "figure"),  # Outputting the figure for the graph
    Output("bbox-data-store", "data"),  # Outputting bbox data to store
    Input("image-table", "selected_rows"),  # New input: selected rows from the table
    Input(
        "image-url-refresh-interval", "n_intervals"
    ),  # Keep interval for potential data refresh
    State("image-keys-store", "data"),
)
def update_webcam_graph_and_data(
    selected_rows,
    n_intervals_url,
    image_keys_data,  # Updated function signature
):
    logger.info(
        f"Triggered: update_webcam_graph_and_data (selected_rows={selected_rows}, url_refresh={n_intervals_url})"
    )

    # Determine the selected image key based on selected_rows
    selected_image_info = None
    if image_keys_data and selected_rows is not None and len(selected_rows) > 0:
        selected_index = selected_rows[0]  # Get the index of the first selected row
        if 0 <= selected_index < len(image_keys_data):
            selected_image_info = image_keys_data[selected_index]
        else:
            logger.warning(
                f"Selected row index {selected_index} is out of bounds for image_keys_data."
            )

    if not selected_image_info:
        logger.info(
            "No image selected or image keys data is empty. Displaying error placeholder."
        )
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
        return fig, {}  # Return empty bbox data

    selected_image_key = selected_image_info["key"]

    # load image from S3
    image_np = load_jpeg_from_s3(s3, S3_BUCKET_NAME, selected_image_key)
    img_height, img_width = image_np.shape[:-1]
    image_pil = Image.fromarray(image_np)
    buffered = io.BytesIO()
    image_pil.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    image_src = f"data:image/png;base64,{img_str}"

    # --- Use cached bbox data ---
    bbox_data_raw = BBOX_JSONS_CACHE.get(selected_image_key, [])

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

            if label not in ALLOWED_CATEGORIES:
                continue

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
            # Draw label above top-left corner of bbox
            fig.add_annotation(
                x=x0_plotly,
                y=y1_plotly,
                xref="paper",
                yref="paper",
                text=label,
                showarrow=False,
                align="left",
                font=dict(color="white", size=10),
                bgcolor=color,
                borderpad=0,
                bordercolor=color,
                borderwidth=2,
                xanchor="left",
                yanchor="bottom",
                opacity=0.7,
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

    return fig, bbox_store_data


# Callback for charts (combined into one for efficiency)
@callback(
    Output("cat_count_graph", "figure"),
    Output("chart-2", "figure"),
    Output("mean_brightness_graph", "figure"),
    Input("image-table", "selected_rows"),  # New input: selected rows from the table
    Input(
        "image-url-refresh-interval", "n_intervals"
    ),  # Keep interval for potential data refresh
    State("image-keys-store", "data"),
)
def update_graphs(selected_rows, n_intervals_url, image_keys_data):
    logger.info(
        f"Triggered: update_graphs (selected_rows={selected_rows}, interval={n_intervals_url})"
    )
    df, distinct_categories = fetch_data()
    color_mapping = generate_color_mapping(distinct_categories)

    # --- Determine Selected Timestamp for filtering ---
    selected_timestamp_dt = None
    selected_image_info = None

    if image_keys_data and selected_rows is not None and len(selected_rows) > 0:
        selected_index = selected_rows[0]  # Get the index of the first selected row
        if 0 <= selected_index < len(image_keys_data):
            selected_image_info = image_keys_data[selected_index]
            timestamp_str_from_key = (
                selected_image_info["key"].split("image_")[-1].split(".jpg")[0]
            )
            try:
                selected_timestamp_dt = pd.to_datetime(
                    timestamp_str_from_key, format="%Y-%m-%d_%H:%M:%S"
                ) + pd.Timedelta(hours=TIME_DIFF)
            except ValueError:
                logger.info(
                    f"Could not parse timestamp from key: {selected_image_info['key']}"
                )
        else:
            logger.warning(
                f"Selected row index {selected_index} is out of bounds for image_keys_data."
            )

    # Cat Count Graph (Bottom-Left)
    if df.empty:
        fig_cat_count = px.scatter()
    else:
        df_filtered = df[df["category_name"] != "whole_image"].copy()
        df_filtered["count"] = pd.to_numeric(df_filtered["count"], errors="coerce")
        df_filtered = df_filtered.sort_values(by=["category_name", "timestamp"])
        fig_cat_count = px.line(
            df_filtered,
            x="timestamp",
            y="count",
            color="category_name",
            color_discrete_map=color_mapping,
            markers=True,
        )
        fig_cat_count.update_layout(
            margin={"r": 0, "t": 40, "l": 0, "b": 0},
            title_x=0.5,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
            ),
        )
        # Add a vertical line or marker for the selected timestamp
        if selected_timestamp_dt:
            fig_cat_count.add_vline(
                x=selected_timestamp_dt,
                line_width=1,
                line_dash="dash",
                line_color="red",
            )

    # New Scatter Plot (Top-Right, formerly chart-2)
    fig_new_scatter = px.scatter()
    if not df.empty and selected_timestamp_dt:
        # Filter df for the selected timestamp AND exclude 'whole_image' category
        df_scatter_data = df[
            (df["timestamp"] == selected_timestamp_dt)
            & (df["category_name"] != "whole_image")
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
                )
                fig_new_scatter.update_layout(
                    margin={"r": 20, "t": 40, "l": 10, "b": 0},
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="center",
                        x=0.5,
                    ),
                )
    elif not df.empty:
        fig_new_scatter = px.scatter(title="Select an image to view object properties")

    # Mean Brightness Graph
    fig_mean_brightness = px.scatter()  # Default empty figure
    if not df.empty:
        # Assuming mean_brightness is associated with 'whole_image' category
        df_brightness = df[df["category_name"] == "whole_image"].copy()
        if not df_brightness.empty:
            df_brightness["mean_brightness"] = pd.to_numeric(
                df_brightness["mean_brightness"], errors="coerce"
            )
            fig_mean_brightness = px.line(
                df_brightness,
                x="timestamp",
                y="mean_brightness",
                title="Mean Brightness Over Time",
                markers=True,
            )
            fig_mean_brightness.update_layout(
                margin={"r": 20, "t": 40, "l": 10, "b": 0},
                title_x=0.5,
            )
            # Add a vertical line or marker for the selected timestamp
            if selected_timestamp_dt:
                fig_mean_brightness.add_vline(
                    x=selected_timestamp_dt,
                    line_width=1,
                    line_dash="dash",
                    line_color="red",
                )
        else:
            fig_mean_brightness = px.scatter(
                title="No 'whole_image' data for Mean Brightness"
            )
    else:  # If df is empty
        fig_mean_brightness = px.scatter(title="No Data Available for Mean Brightness")

    return fig_cat_count, fig_new_scatter, fig_mean_brightness


if __name__ == "__main__":
    app.run(debug=DEBUG)
