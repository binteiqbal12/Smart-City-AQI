import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv

from open_aq_data import get_locations

load_dotenv()

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")


def get_connection():
    return snowflake.connector.connect(
        account=SNOWFLAKE_ACCOUNT,
        user=SNOWFLAKE_USER,
        password=SNOWFLAKE_PASSWORD,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=SNOWFLAKE_DATABASE,
        schema=SNOWFLAKE_SCHEMA,
    )


def load_dataframe_to_snowflake(df: pd.DataFrame, table_name: str):
    if df.empty:
        print("DataFrame is empty, nothing to load.")
        return

    df.columns = [col.upper() for col in df.columns]

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            ID VARCHAR,
            NAME VARCHAR,
            CITY VARCHAR,
            COUNTRY VARCHAR,
            PROVIDER VARCHAR,
            LATITUDE FLOAT,
            LONGITUDE FLOAT
        )
        """
        cursor.execute(create_table_sql)

        success, nchunks, nrows, _ = write_pandas(conn, df, table_name)
        print(f"Success: {success}, rows loaded: {nrows}")

    finally:
        conn.close()


if __name__ == "__main__":
    df = get_locations(limit=100)
    load_dataframe_to_snowflake(df, "OPENAQ_LOCATIONS")