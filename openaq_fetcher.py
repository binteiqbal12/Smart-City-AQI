import os
import time
import requests
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")
BASE_URL = "https://api.openaq.org/v3"

headers = {
    "X-API-Key": OPENAQ_API_KEY
}

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_connection():
    return snowflake.connector.connect(
        account=SNOWFLAKE_ACCOUNT,
        user=SNOWFLAKE_USER,
        password=SNOWFLAKE_PASSWORD,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=SNOWFLAKE_DATABASE,
        schema=SNOWFLAKE_SCHEMA,
    )


def get_pakistan_locations(limit=100):
    url = f"{BASE_URL}/locations"
    params = {"iso": "PK", "limit": limit}

    try:
        response = session.get(url, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        print("Failed to fetch locations:", e)
        return []

    time.sleep(1)

    if response.status_code != 200:
        print("Error fetching locations:", response.text)
        return []

    return response.json()["results"]


def get_sensors_for_location(location_id):
    url = f"{BASE_URL}/locations/{location_id}/sensors"

    try:
        response = session.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Skipping sensors for location {location_id} (network error): {e}")
        return []

    time.sleep(1)

    if response.status_code != 200:
        print(f"Error fetching sensors for location {location_id}:", response.text)
        return []

    return response.json()["results"]


def get_latest_for_location(location_id):
    url = f"{BASE_URL}/locations/{location_id}/latest"

    try:
        response = session.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Skipping latest for location {location_id} (network error): {e}")
        return []

    time.sleep(1)

    if response.status_code != 200:
        print(f"Error fetching latest for location {location_id}:", response.text)
        return []

    return response.json()["results"]


def build_openaq_records():
    records = []
    locations = get_pakistan_locations()

    print(f"Found {len(locations)} Pakistan locations")

    for i, loc in enumerate(locations, start=1):
        location_id = loc.get("id")
        station_name = loc.get("name")
        city = loc.get("locality")
        country_code = loc.get("country", {}).get("code")
        latitude = loc.get("coordinates", {}).get("latitude")
        longitude = loc.get("coordinates", {}).get("longitude")

        print(f"[{i}/{len(locations)}] Processing location {location_id} ({station_name})")

        try:
            sensors = get_sensors_for_location(location_id)
            sensor_map = {}
            for s in sensors:
                sensor_map[s.get("id")] = {
                    "parameter": s.get("parameter", {}).get("name"),
                    "units": s.get("parameter", {}).get("units"),
                }

            latest_readings = get_latest_for_location(location_id)

            for reading in latest_readings:
                sensor_id = reading.get("sensorsId") or reading.get("sensor_id")
                sensor_info = sensor_map.get(sensor_id, {})
                pollutant_type = sensor_info.get("parameter")

                if pollutant_type not in ("pm25", "pm10"):
                    continue

                value = reading.get("value")
                if value is None or value < 0:
                    continue

                records.append({
                    "LOCATION_ID": location_id,
                    "STATION_NAME": station_name,
                    "CITY": city,
                    "COUNTRY_CODE": country_code,
                    "LATITUDE": latitude,
                    "LONGITUDE": longitude,
                    "POLLUTANT_TYPE": pollutant_type,
                    "POLLUTANT_VALUE": value,
                    "UNIT": sensor_info.get("units"),
                    "RECORDED_AT": reading.get("datetime", {}).get("utc"),
                })

        except Exception as e:
            print(f"Unexpected error on location {location_id}, skipping: {e}")
            continue

    return pd.DataFrame(records)


def load_to_snowflake(df: pd.DataFrame, table_name="OPENAQ_RAW"):
    if df.empty:
        print("No data to load.")
        return

    conn = get_connection()
    try:
        success, nchunks, nrows, _ = write_pandas(conn, df, table_name)
        print(f"Success: {success}, rows loaded: {nrows}")
    finally:
        conn.close()


if __name__ == "__main__":
    df = build_openaq_records()
    print(df.head(20))
    print(f"Total records: {len(df)}")

    csv_path = "openaq_readings.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved to {csv_path}")

    load_to_snowflake(df)