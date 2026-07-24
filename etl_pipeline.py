import os
import time
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv

load_dotenv()

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")

AQI_CATEGORY_MAP = [
    (0, 50, "Good", "LOW"),
    (51, 100, "Moderate", "LOW"),
    (101, 150, "Unhealthy for Sensitive Groups", "MEDIUM"),
    (151, 200, "Unhealthy", "HIGH"),
    (201, 300, "Very Unhealthy", "HIGH"),
    (301, 500, "Hazardous", "CRITICAL"),
]


def get_connection(schema="RAW", max_retries=5):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return snowflake.connector.connect(
                account=SNOWFLAKE_ACCOUNT,
                user=SNOWFLAKE_USER,
                password=SNOWFLAKE_PASSWORD,
                warehouse=SNOWFLAKE_WAREHOUSE,
                database=SNOWFLAKE_DATABASE,
                schema=schema,
                login_timeout=15,
            )
        except Exception as e:
            last_error = e
            print(f"  Connection attempt {attempt}/{max_retries} failed: {type(e).__name__}")
            if attempt < max_retries:
                wait = 5 * attempt
                print(f"  Retrying in {wait} seconds...")
                time.sleep(wait)
    print("  All connection attempts failed.")
    raise last_error


def categorize_aqi(aqi_value):
    if pd.isna(aqi_value):
        return None, None
    for lo, hi, category, risk in AQI_CATEGORY_MAP:
        if lo <= aqi_value <= hi:
            return category, risk
    if aqi_value > 500:
        return "Hazardous", "CRITICAL"
    return None, None


def calculate_aqi_from_pm25(pm25):
    breakpoints = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 500.4, 301, 500),
    ]
    pm25 = max(0.0, min(pm25, 500.4))
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= pm25 <= c_hi:
            return round(((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo, 1)
    return 500.0


def load_raw_tables():
    conn = get_connection(schema="RAW")
    try:
        iot_df = pd.read_sql("SELECT * FROM IOT_READINGS", conn)
        openaq_df = pd.read_sql("SELECT * FROM OPENAQ_RAW", conn)
    finally:
        conn.close()
    return iot_df, openaq_df


def clean_iot_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]

    df = df.dropna(subset=["PM25", "AQI_VALUE"])

    df = df[
        (df["PM25"] >= 0) & (df["PM25"] <= 500) &
        (df["CO2_PPM"] >= 400) & (df["CO2_PPM"] <= 2000) &
        (df["HUMIDITY_PCT"] >= 0) & (df["HUMIDITY_PCT"] <= 100)
    ]

    categories = df["AQI_VALUE"].apply(categorize_aqi)
    df["AQI_CATEGORY"] = categories.apply(lambda x: x[0])
    df["HEALTH_RISK"] = categories.apply(lambda x: x[1])

    df = df.drop_duplicates(subset=["SENSOR_ID", "RECORDED_AT"])

    # Force clean datetime dtype right here at the source
    df["RECORDED_AT"] = pd.to_datetime(df["RECORDED_AT"], errors="coerce")

    result = pd.DataFrame({
        "SOURCE": "iot_simulator",
        "CITY": df["CITY"],
        "SENSOR_ID": df["SENSOR_ID"],
        "PM25": df["PM25"],
        "PM10": df["PM10"],
        "CO2_PPM": df["CO2_PPM"],
        "AQI_VALUE": df["AQI_VALUE"],
        "AQI_CATEGORY": df["AQI_CATEGORY"],
        "HEALTH_RISK": df["HEALTH_RISK"],
        "LATITUDE": pd.array([None] * len(df), dtype="Float64"),
        "LONGITUDE": pd.array([None] * len(df), dtype="Float64"),
        "RECORDED_AT": df["RECORDED_AT"].values,
    })

    return result


def clean_openaq_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]

    df = df[df["POLLUTANT_TYPE"].isin(["pm25", "pm10"])]
    df = df[df["POLLUTANT_VALUE"] > 0]

    df["RECORDED_AT"] = pd.to_datetime(df["RECORDED_AT"], utc=True, errors="coerce")
    df["RECORDED_AT"] = df["RECORDED_AT"].dt.tz_localize(None)
    df = df.dropna(subset=["RECORDED_AT"])

    df["CITY"] = df["CITY"].fillna("Unknown")
    df["STATION_NAME"] = df["STATION_NAME"].fillna("Unknown")
    df["LATITUDE"] = df["LATITUDE"].fillna(-999)
    df["LONGITUDE"] = df["LONGITUDE"].fillna(-999)

    pivot = df.pivot_table(
        index=["LOCATION_ID", "STATION_NAME", "CITY", "LATITUDE", "LONGITUDE", "RECORDED_AT"],
        columns="POLLUTANT_TYPE",
        values="POLLUTANT_VALUE",
        aggfunc="first",
    ).reset_index()

    pivot.columns.name = None
    pivot["LATITUDE"] = pivot["LATITUDE"].replace(-999, pd.NA)
    pivot["LONGITUDE"] = pivot["LONGITUDE"].replace(-999, pd.NA)
    pivot["CITY"] = pivot["CITY"].replace("Unknown", pd.NA)

    if "pm25" not in pivot.columns:
        pivot["pm25"] = None
    if "pm10" not in pivot.columns:
        pivot["pm10"] = None

    pivot["AQI_VALUE"] = pivot["pm25"].apply(
        lambda v: calculate_aqi_from_pm25(v) if pd.notna(v) else None
    )
    categories = pivot["AQI_VALUE"].apply(categorize_aqi)
    pivot["AQI_CATEGORY"] = categories.apply(lambda x: x[0])
    pivot["HEALTH_RISK"] = categories.apply(lambda x: x[1])

    pivot = pivot.drop_duplicates(subset=["LOCATION_ID", "RECORDED_AT"])

    # Force clean datetime dtype right here at the source too
    pivot["RECORDED_AT"] = pd.to_datetime(pivot["RECORDED_AT"], errors="coerce")

    result = pd.DataFrame({
        "SOURCE": "openaq_v3",
        "CITY": pivot["CITY"],
        "SENSOR_ID": pd.array([None] * len(pivot), dtype="object"),
        "PM25": pivot["pm25"],
        "PM10": pivot["pm10"],
        "CO2_PPM": pd.array([None] * len(pivot), dtype="Float64"),
        "AQI_VALUE": pivot["AQI_VALUE"],
        "AQI_CATEGORY": pivot["AQI_CATEGORY"],
        "HEALTH_RISK": pivot["HEALTH_RISK"],
        "LATITUDE": pivot["LATITUDE"],
        "LONGITUDE": pivot["LONGITUDE"],
        "RECORDED_AT": pivot["RECORDED_AT"].values,
    })

    return result


def load_to_silver(df: pd.DataFrame):
    if df.empty:
        print("No cleaned data to load.")
        return

    df["RECORDED_AT"] = pd.to_datetime(df["RECORDED_AT"], errors="coerce")
    df = df.dropna(subset=["RECORDED_AT"])
    df["RECORDED_AT"] = df["RECORDED_AT"].dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    conn = get_connection(schema="CLEAN")
    try:
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE IF EXISTS AQI_CLEAN")
        success, nchunks, nrows, _ = write_pandas(conn, df, "AQI_CLEAN")
        print(f"Success: {success}, rows loaded to CLEAN.AQI_CLEAN: {nrows}")
    finally:
        conn.close()


if __name__ == "__main__":
    print("Loading raw data from Bronze layer...")
    iot_raw, openaq_raw = load_raw_tables()
    print(f"  IOT_READINGS: {len(iot_raw)} rows")
    print(f"  OPENAQ_RAW: {len(openaq_raw)} rows")

    print("Cleaning IoT data...")
    iot_clean = clean_iot_data(iot_raw)
    print(f"  -> {len(iot_clean)} rows after cleaning")
    print(f"  RECORDED_AT dtype: {iot_clean['RECORDED_AT'].dtype}")

    print("Cleaning OpenAQ data...")
    openaq_clean = clean_openaq_data(openaq_raw)
    print(f"  -> {len(openaq_clean)} rows after cleaning")
    print(f"  RECORDED_AT dtype: {openaq_clean['RECORDED_AT'].dtype}")

    print("Combining sources...")
    combined = pd.concat([iot_clean, openaq_clean], ignore_index=True)

    # Final safety net: force one clean, consistent datetime dtype
    combined["RECORDED_AT"] = pd.to_datetime(combined["RECORDED_AT"], errors="coerce")
    combined = combined.dropna(subset=["RECORDED_AT"])
    print(f"  Combined RECORDED_AT dtype: {combined['RECORDED_AT'].dtype}")

    combined["PROCESSED_AT"] = pd.Timestamp.utcnow().tz_localize(None)
    print(f"  -> {len(combined)} total rows")

    print(combined[["SOURCE", "CITY", "RECORDED_AT"]].head(10))

    print("Loading to Silver layer (CLEAN.AQI_CLEAN)...")
    load_to_silver(combined)