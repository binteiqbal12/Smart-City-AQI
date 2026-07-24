import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
import os
from dotenv import load_dotenv

load_dotenv()

conn = snowflake.connector.connect(
    account=os.getenv("SNOWFLAKE_ACCOUNT"),
    user=os.getenv("SNOWFLAKE_USER"),
    password=os.getenv("SNOWFLAKE_PASSWORD"),
    warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
    database=os.getenv("SNOWFLAKE_DATABASE"),
    schema=os.getenv("SNOWFLAKE_SCHEMA"),
)

df = pd.read_csv("iot_readings.csv")
df.columns = [c.upper() for c in df.columns]

cursor = conn.cursor()
cursor.execute("TRUNCATE TABLE IOT_READINGS")

success, nchunks, nrows, _ = write_pandas(conn, df, "IOT_READINGS")
print(f"Success: {success}, rows loaded: {nrows}")

conn.close()
