import pandas as pd
from openaq_fetcher import load_to_snowflake

df = pd.read_csv("openaq_readings.csv")
load_to_snowflake(df)