import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")

BASE_URL = "https://api.openaq.org/v3/locations"

headers = {
    "X-API-Key": OPENAQ_API_KEY
}


def get_locations(country="PK", limit=10):

    params = {
        "iso": country,
        "limit": limit
    }

    response = requests.get(BASE_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()["results"]
        records = []
        for row in data:
            records.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "city": row.get("locality"),
                "country": row.get("country", {}).get("name"),
                "provider": row.get("provider", {}).get("name"),
                "latitude": row.get("coordinates", {}).get("latitude"),
                "longitude": row.get("coordinates", {}).get("longitude"),
            })
        return pd.DataFrame(records)
    else:
        print(response.text)
        return pd.DataFrame()


if __name__ == "__main__":
    df = get_locations(limit=100)
    print(df)