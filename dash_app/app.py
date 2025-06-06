import os

import boto3
import dash
import pandas as pd
import plotly.express as px
from dash import Input, Output, dcc, html

REGION_NAME = os.getenv("TF_VAR_region")
SRC_TABLE = os.getenv("TF_VAR_db_img_stats_table")

dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
table = dynamodb.Table(SRC_TABLE)


# Function to read data from DynamoDB
def fetch_data():
    response = table.scan()
    items = response["Items"]
    # Convert to DataFrame
    df = pd.DataFrame(items)

    # Convert 'id' to datetime if needed
    if "id" in df.columns:
        df["id"] = pd.to_datetime(df["id"], format="%Y-%m-%d_%H:%M:%S")

    df = df.sort_values(by="id")

    return df


# Dash app
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
                    },
                )
            ],
        ),
        # This is the main grid container
        html.Div(
            style={
                "display": "grid",
                "grid-template-columns": "1fr 1fr",  # Two equal-width columns
                "grid-template-rows": "1fr 1fr",  # Two equal-height rows
                "gap": "20px",  # Space between grid items
                "height": "80vh",  # Make the grid fill most of the viewport height
                "width": "90vw",  # Make the grid fill most of the viewport width
                "margin": "auto",  # Center the grid container horizontally
                "padding": "15px",  # Padding around the grid
                "border": "1px solid #ddd",  # Optional: for visual debugging
                "borderRadius": "8px",
                "boxShadow": "2px 2px 10px rgba(0,0,0,0.1)",
            },
            children=[
                # Top-Left Cell: Image (Webcam Feed)
                html.Div(
                    style={
                        "backgroundColor": "#f9f9f9",
                        "display": "flex",
                        "justifyContent": "center",
                        "alignItems": "center",
                        "overflow": "hidden",  # Hide overflow if image is too big
                        "borderRadius": "8px",
                        "border": "1px solid #eee",
                    },
                    children=[
                        # Placeholder for the webcam image.
                        # In a real app, 'src' would be updated via a callback
                        # pointing to a Flask endpoint serving the webcam feed.
                        html.Img(
                            src="/assets/placeholder_webcam.png",  # You need to place an image here in an 'assets' folder
                            id="webcam-feed",
                            alt="Webcam Feed",
                            style={
                                "maxWidth": "100%",
                                "maxHeight": "100%",
                                "objectFit": "contain",
                            },
                        )
                    ],
                ),
                # Top-Right Cell: Chart 1 (Original cat_count_graph)
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
                # Bottom-Left Cell: Chart 2
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
                # Bottom-Right Cell: Chart 3
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
    ],
    style={
        "backgroundColor": "#e6e5e5cc",
    },
)


@app.callback(Output("cat_count_graph", "figure"), Input("refresh-btn", "n_clicks"))
def update_graph(n_clicks):
    df = fetch_data()
    if df.empty:
        return px.scatter(title="No Data")

    df_filtered = df[df["category_name"] != "whole_image"]
    df_filtered["count"] = pd.to_numeric(df_filtered["count"], errors="coerce")

    fig = px.line(
        df_filtered,
        x="id",
        y="count",
        color="category_name",
        markers=True,
        title="Category Counts Over Time",
    )

    return fig


if __name__ == "__main__":
    app.run(debug=True)
