import os
import time
import math
import random
import csv
from datetime import datetime, timezone
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")

CSV_PATH = "iot_readings.csv"

# ---- Sensor network spec ----
SENSORS = [
    {"sensor_id": "PKS_KHI_IND_01", "city": "Karachi",   "zone_type": "industrial"},
    {"sensor_id": "PKS_KHI_TRF_02", "city": "Karachi",   "zone_type": "traffic"},
    {"sensor_id": "PKS_LHR_RES_01", "city": "Lahore",    "zone_type": "residential"},
    {"sensor_id": "PKS_LHR_IND_02", "city": "Lahore",    "zone_type": "industrial"},
    {"sensor_id": "PKS_ISB_PRK_01", "city": "Islamabad", "zone_type": "park"},
    {"sensor_id": "PKS_ISB_TRF_02", "city": "Islamabad", "zone_type": "traffic"},
    {"sensor_id": "PKS_PEW_IND_01", "city": "Peshawar",  "zone_type": "industrial"},
    {"sensor_id": "PKS_PEW_RES_02", "city": "Peshawar",  "zone_type": "residential"},
    {"sensor_id": "PKS_MUL_TRF_01", "city": "Multan",    "zone_type": "traffic"},
    {"sensor_id": "PKS_MUL_PRK_02", "city": "Multan",    "zone_type": "park"},
]

# ---- Zone base ranges: (pm25_low, pm25_high, co2_low, co2_high, temp_low, temp_high) ----
ZONE_BASE = {
    "industrial":  {"pm25": (80, 120), "co2": (600, 900), "temp": (30, 42)},
    "traffic":     {"pm25": (55, 80),  "co2": (500, 700), "temp": (28, 40)},
    "residential": {"pm25": (25, 50),  "co2": (420, 500), "temp": (25, 38)},
    "park":        {"pm25": (8, 20),   "co2": (400, 430), "temp": (22, 35)},
}

# ---- AQI breakpoints (EPA standard, PM2.5) ----
# (C_lo, C_hi, I_lo, I_hi, severity_label)
AQI_BREAKPOINTS = [
    (0.0, 12.0, 0, 50, "GOOD"),
    (12.1, 35.4, 51, 100, "MODERATE"),
    (35.5, 55.4, 101, 150, "UNHEALTHY FOR SENSITIVE"),
    (55.5, 150.4, 151, 200, "UNHEALTHY"),
    (150.5, 250.4, 201, 300, "VERY UNHEALTHY"),
    (250.5, 500.4, 301, 500, "HAZARDOUS"),
]


def calculate_aqi(pm25):
    """EPA formula: AQI = ((I_hi - I_lo) / (C_hi - C_lo)) * (PM2.5 - C_lo) + I_lo"""
    pm25 = max(0.0, min(pm25, 500.4))  # clamp to valid range

    for c_lo, c_hi, i_lo, i_hi, severity in AQI_BREAKPOINTS:
        if c_lo <= pm25 <= c_hi:
            aqi = ((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo
            return round(aqi, 1), severity

    # fallback (shouldn't hit if pm25 clamped correctly)
    return 500.0, "HAZARDOUS"


def time_of_day_multiplier():
    """Peaks at 8am and 6pm: 1.0 + 0.3 * sin((hour - 8) * pi / 12)"""
    hour = datetime.now().hour
    return 1.0 + 0.3 * math.sin((hour - 8) * math.pi / 12)


def generate_reading(sensor):
    zone = sensor["zone_type"]
    base = ZONE_BASE[zone]

    tod_mult = time_of_day_multiplier()

    # base values with time-of-day effect
    pm25 = random.uniform(*base["pm25"]) * tod_mult
    co2 = random.uniform(*base["co2"]) * tod_mult
    temp = random.uniform(*base["temp"])

    # +/-15% random noise
    pm25 *= random.uniform(0.85, 1.15)
    co2 *= random.uniform(0.85, 1.15)
    temp *= random.uniform(0.85, 1.15)

    # 15% chance of anomaly spike (2.5x - 4.0x pm25)
    if random.random() < 0.15:
        pm25 *= random.uniform(2.5, 4.0)

    # clamp to spec ranges
    pm25 = max(0.0, min(pm25, 500.0))
    pm10 = max(pm25, pm25 * random.uniform(1.05, 1.3))  # pm10 always >= pm25
    pm10 = min(pm10, 600.0)
    co2 = max(400.0, min(co2, 2000.0))
    temp = max(15.0, min(temp, 45.0))
    humidity = random.uniform(10, 90)
    wind_speed = random.uniform(0, 60)

    aqi_value, severity = calculate_aqi(pm25)

    return {
        "sensor_id": sensor["sensor_id"],
        "city": sensor["city"],
        "zone_type": zone,
        "pm25": round(pm25, 2),
        "pm10": round(pm10, 2),
        "co2_ppm": round(co2, 2),
        "temperature_c": round(temp, 2),
        "humidity_pct": round(humidity, 2),
        "wind_speed_kmh": round(wind_speed, 2),
        "aqi_value": aqi_value,
        "severity": severity,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def get_connection():
    return snowflake.connector.connect(
        account=SNOWFLAKE_ACCOUNT,
        user=SNOWFLAKE_USER,
        password=SNOWFLAKE_PASSWORD,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=SNOWFLAKE_DATABASE,
        schema=SNOWFLAKE_SCHEMA,
    )


def init_csv():
    file_exists = os.path.isfile(CSV_PATH)
    if not file_exists:
        with open(CSV_PATH, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "sensor_id", "city", "zone_type", "pm25", "pm10", "co2_ppm",
                "temperature_c", "humidity_pct", "wind_speed_kmh",
                "aqi_value", "severity", "recorded_at"
            ])
            writer.writeheader()


def save_to_csv(readings):
    with open(CSV_PATH, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sensor_id", "city", "zone_type", "pm25", "pm10", "co2_ppm",
            "temperature_c", "humidity_pct", "wind_speed_kmh",
            "aqi_value", "severity", "recorded_at"
        ])
        for row in readings:
            writer.writerow(row)


def save_to_snowflake(readings):
    df = pd.DataFrame(readings)
    df.columns = [c.upper() for c in df.columns]

    try:
        conn = get_connection()
        try:
            success, nchunks, nrows, _ = write_pandas(conn, df, "IOT_READINGS")
            print(f"  [Snowflake] inserted {nrows} rows")
        finally:
            conn.close()
    except Exception as e:
        print(f"  [Snowflake] insert failed (will retry next loop): {e}")


def run_simulator(duration_minutes=30, interval_seconds=10):
    init_csv()
    end_time = time.time() + duration_minutes * 60
    loop_count = 0

    print(f"Starting IoT simulator for {duration_minutes} minutes, "
          f"generating {len(SENSORS)} readings every {interval_seconds}s...")

    while time.time() < end_time:
        loop_count += 1
        readings = [generate_reading(sensor) for sensor in SENSORS]

        for r in readings:
            if r["severity"] in ("UNHEALTHY", "VERY UNHEALTHY", "HAZARDOUS"):
                print(f"  ALERT [{r['severity']}] {r['sensor_id']} ({r['city']}) "
                      f"AQI={r['aqi_value']} PM2.5={r['pm25']}")

        save_to_csv(readings)
        save_to_snowflake(readings)

        print(f"Loop {loop_count} complete — {len(readings)} readings generated at "
              f"{datetime.now().strftime('%H:%M:%S')}")

        time.sleep(interval_seconds)

    print("Simulator finished.")


if __name__ == "__main__":
    run_simulator(duration_minutes=30, interval_seconds=10)