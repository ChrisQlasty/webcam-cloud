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

    return df


# Dash app
app = dash.Dash(__name__)
app.title = "DynamoDB Dashboard"

app.layout = html.Div(
    [
        html.H1("DynamoDB Dashboard"),
        html.Button("Refresh Data", id="refresh-btn", n_clicks=0),
        dcc.Graph(id="my-graph"),
    ]
)


@app.callback(Output("my-graph", "figure"), Input("refresh-btn", "n_clicks"))
def update_graph(n_clicks):
    df = fetch_data()
    if df.empty:
        return px.scatter(title="No Data")

    # Example: group by category and count
    if "category_name" in df.columns:
        grouped = df.groupby("category_name").size().reset_index(name="count")
        fig = px.bar(grouped, x="category_name", y="count", title="Count by Category")
    else:
        fig = px.scatter(title="Missing 'category_name' field")

    return fig


if __name__ == "__main__":
    app.run(debug=True)
