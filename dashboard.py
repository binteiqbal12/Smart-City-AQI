import os
import streamlit as st
import pandas as pd
import snowflake.connector
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------

st.set_page_config(
    page_title="Smart City AQI Dashboard",
    page_icon="🌍",
    layout="wide"
)

# ---------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------

load_dotenv()


# ---------------------------------------------------
# TITLE
# ---------------------------------------------------

st.title("🌍 Smart City Air Quality Dashboard")
st.write("### Live AQI Analytics from Snowflake Gold Layer")

from datetime import datetime

st.caption(
    f"Last Updated: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}"
)

# ---------------------------------------------------
# SNOWFLAKE CONNECTION
# ---------------------------------------------------

def get_connection():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema="ANALYTICS"
    )

# ---------------------------------------------------
# AQI STATUS FUNCTION
# ---------------------------------------------------

def get_aqi_status(aqi):

    if aqi <= 50:
        return "🟢 Good"

    elif aqi <= 100:
        return "🟡 Moderate"

    elif aqi <= 150:
        return "🟠 Unhealthy for Sensitive Groups"

    elif aqi <= 200:
        return "🔴 Unhealthy"

    elif aqi <= 300:
        return "🟣 Very Unhealthy"

    else:
        return "⚫ Hazardous"

# ---------------------------------------------------
# LOAD DATA
# ---------------------------------------------------

@st.cache_data(ttl=60)
def load_data():

    conn = get_connection()

    query = """
        SELECT *
        FROM CITY_DAILY
        ORDER BY CITY;
    """

    df = pd.read_sql_query(query, conn)

    conn.close()

    return df

# ---------------------------------------------------
# MAIN APP
# ---------------------------------------------------

try:
    df = load_data()

    # Latitude and Longitude for Pakistani cities
    city_coordinates = {
        "Islamabad": {"LAT": 33.6844, "LON": 73.0479},
        "Lahore": {"LAT": 31.5204, "LON": 74.3587},
        "Karachi": {"LAT": 24.8607, "LON": 67.0011},
        "Peshawar": {"LAT": 34.0151, "LON": 71.5249},
        "Multan": {"LAT": 30.1575, "LON": 71.5249},
    }

    df["LAT"] = df["CITY"].map(lambda x: city_coordinates[x]["LAT"])
    df["LON"] = df["CITY"].map(lambda x: city_coordinates[x]["LON"])

    df["AQI_STATUS"] = df["AVG_AQI"].apply(get_aqi_status)

    df["AVG_AQI"] = df["AVG_AQI"].round(1)
    df["MAX_AQI"] = df["MAX_AQI"].round(1)
    df["MIN_AQI"] = df["MIN_AQI"].round(1)

    st.success(f"Loaded {len(df)} records")

    st.divider()

    # ---------------------------------------------------
    # SIDEBAR
    # ---------------------------------------------------

    st.sidebar.header("Filters")

    selected_city = st.sidebar.selectbox(
        "Select City",
        ["All"] + sorted(df["CITY"].unique())
    )

    if selected_city != "All":
        df = df[df["CITY"] == selected_city]

    if st.sidebar.button("🔄 Refresh Data"):
       st.cache_data.clear()
       st.toast("Data refreshed successfully!")
       st.rerun()

    # ---------------------------------------------------
    # KPI CARDS
    # ---------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("🏙 Cities", df["CITY"].nunique())

    col2.metric(
        "📊 Average AQI",
        round(df["AVG_AQI"].mean(), 1)
    )

    col3.metric(
        "📈 Maximum AQI",
        round(df["MAX_AQI"].max(), 1)
    )

    col4.metric(
        "📉 Minimum AQI",
        round(df["MIN_AQI"].min(), 1)
    )

    # ---------------------------------------------------
# BEST & WORST AQI
# ---------------------------------------------------

    best_city = df.loc[df["AVG_AQI"].idxmin()]
    worst_city = df.loc[df["AVG_AQI"].idxmax()]

    st.subheader("🏆 Air Quality Highlights")

    best_col, worst_col = st.columns(2)

    with best_col:
      st.success(
        f"""
    ### 🏆 Best Air Quality

    **City:** {best_city['CITY']}

    **Average AQI:** {best_city['AVG_AQI']}

    **Status:** {best_city['AQI_STATUS']}
    """
    )

    with worst_col:
      st.error(
        f"""
    ### ⚠️ Worst Air Quality

    **City:** {worst_city['CITY']}

    **Average AQI:** {worst_city['AVG_AQI']}

    **Status:** {worst_city['AQI_STATUS']}
    """
    )

    st.divider()

# ---------------------------------------------------
# AQI GAUGE
# ---------------------------------------------------

    st.subheader("🌡️ Overall Air Quality Index")

    avg_aqi = round(df["AVG_AQI"].mean(), 1)

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=avg_aqi,
            number={"suffix": " AQI", "font": {"size": 48}},
            title={
                "text": "<b>Overall Average AQI</b>",
                "font": {"size": 24}
            },
            gauge={
               "shape": "angular",
                "axis": {
                  "range": [0, 500],
                  "tickwidth": 2,
                  "tickcolor": "gray"
               },

            # Hide the blue progress bar
            "bar": {
                "color": "rgba(0,0,0,0)"
            },

            "steps": [
                {"range": [0, 50], "color": "#00C853"},      # Green
                {"range": [50, 100], "color": "#FFD600"},    # Yellow
                {"range": [100, 150], "color": "#FF9100"},   # Orange
                {"range": [150, 200], "color": "#F44336"},   # Red
                {"range": [200, 300], "color": "#8E24AA"},   # Purple
                {"range": [300, 500], "color": "#6D0000"}    # Dark Red
            ],

            "threshold": {
                "line": {
                    "color": "black",
                    "width": 6
                },
                "thickness": 0.9,
                "value": avg_aqi
            }
        }
    )
)

    gauge.update_layout(
        height=420,
        margin=dict(l=30, r=30, t=60, b=20),
        paper_bgcolor="white",
        font={"family": "Arial"}
    )

    st.plotly_chart(gauge, use_container_width=True)
    # ---------------------------------------------------
    # BAR CHART
    # ---------------------------------------------------

    st.subheader("📊 Average AQI by City")

    fig = px.bar(
        df.sort_values("AVG_AQI", ascending=False),
        x="CITY",
        y="AVG_AQI",
        text="AVG_AQI",
        color="AQI_STATUS",
        color_discrete_map={
            "🟢 Good": "green",
            "🟡 Moderate": "gold",
            "🟠 Unhealthy for Sensitive Groups": "orange",
            "🔴 Unhealthy": "red",
            "🟣 Very Unhealthy": "purple",
            "⚫ Hazardous": "maroon"
    }
    )

    fig.update_traces(
        textposition="outside",
        texttemplate="%{text}"
    )

    fig.update_layout(
        height=500,
        xaxis_title="City",
        yaxis_title="Average AQI"
    )

    st.plotly_chart(fig, use_container_width=True)

    # ---------------------------------------------------
    # LINE CHART
    # ---------------------------------------------------

    st.subheader("📈 Maximum AQI by City")

    fig2 = px.line(
        df.sort_values("MAX_AQI", ascending=False),
        x="CITY",
        y="MAX_AQI",
        text="MAX_AQI",
        markers=True
    )

    fig2.update_traces(
        mode="lines+markers+text",
        textposition="top center",
        line=dict(width=4),
        marker=dict(size=10)
    )

    fig2.update_layout(
        height=500,
        xaxis_title="City",
        yaxis_title="Maximum AQI"
    )

    st.plotly_chart(fig2, use_container_width=True)

    # ---------------------------------------------------
    # PIE CHART
    # ---------------------------------------------------

    st.subheader("🥧 AQI Status Distribution")

    pie = px.pie(
        df,
        names="AQI_STATUS",
        title="Cities by AQI Category",
        color="AQI_STATUS",
        color_discrete_map={
             "🟢 Good": "green",
             "🟡 Moderate": "gold",
             "🟠 Unhealthy for Sensitive Groups": "orange",
             "🔴 Unhealthy": "red",
             "🟣 Very Unhealthy": "purple",
             "⚫ Hazardous": "maroon"
        }
    )

    st.plotly_chart(
        pie,
        use_container_width=True
    )

    # ---------------------------------------------------
    # PAKISTAN AQI MAP
    # ---------------------------------------------------

    st.subheader("🗺️ Pakistan AQI Map")

    fig_map = px.scatter_mapbox(
        df,
        lat="LAT",
        lon="LON",
        hover_name="CITY",
        hover_data={
            "AVG_AQI": True,
            "MAX_AQI": True,
            "MIN_AQI": True,
            "LAT": False,
            "LON": False,
        },
        color="AVG_AQI",
        size="AVG_AQI",
        color_continuous_scale="RdYlGn_r",
        zoom=4.8,
        center={"lat": 30.5, "lon": 69.5},
        height=600,
    )

    fig_map.update_layout(
        mapbox_style="open-street-map",
        margin=dict(l=0, r=0, t=30, b=0)
    )

    st.plotly_chart(fig_map, use_container_width=True)

    # ---------------------------------------------------
    # DATA TABLE
    # ---------------------------------------------------

    st.subheader("📋 City AQI Data")

    st.dataframe(
        df[
            [
                "CITY",
                "AVG_AQI",
                "MAX_AQI",
                "MIN_AQI",
                "AQI_STATUS"
            ]
        ].sort_values(
            by="AVG_AQI",
            ascending=False
        ),
        use_container_width=True,
        hide_index=True
    )

    # ---------------------------------------------------
    # DOWNLOAD BUTTON
    # ---------------------------------------------------

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="📥 Download AQI Data (CSV)",
        data=csv,
        file_name="city_aqi_data.csv",
        mime="text/csv"
    )

    # ---------------------------------------------------
    # FOOTER
    # ---------------------------------------------------

    st.markdown("---")

    st.caption(
        "Developed by Aqsa Khan | Smart City AQI Analytics Dashboard"
    )

except Exception as e:
    st.error("Unable to load data from Snowflake.")
    st.exception(e)
    
