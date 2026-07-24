"""
Sample ETL Pipeline DAG
------------------------
A simple Extract -> Transform -> Load example to verify your Airflow
setup is working correctly.
"""

from airflow.sdk import dag, task
from datetime import datetime


@dag(
    dag_id="sample_etl_pipeline",
    description="A simple sample ETL pipeline for testing",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example", "etl"],
)
def sample_etl_pipeline():

    @task
    def extract():
        """Simulate pulling raw data from a source."""
        raw_data = [
            {"id": 1, "name": "apple", "price": 1.5},
            {"id": 2, "name": "banana", "price": 0.5},
            {"id": 3, "name": "cherry", "price": 3.0},
        ]
        print(f"Extracted {len(raw_data)} records")
        return raw_data

    @task
    def transform(raw_data: list):
        """Apply a simple transformation (e.g. add tax)."""
        transformed = []
        for item in raw_data:
            item = item.copy()
            item["price_with_tax"] = round(item["price"] * 1.1, 2)
            transformed.append(item)
        print(f"Transformed {len(transformed)} records")
        return transformed

    @task
    def load(transformed_data: list):
        """Simulate loading data into a destination (e.g. DB, file, warehouse)."""
        for item in transformed_data:
            print(f"Loading record: {item}")
        print(f"Loaded {len(transformed_data)} records successfully")

    # Define task dependencies
    raw = extract()
    transformed = transform(raw)
    load(transformed)


sample_etl_pipeline()