
import json
import sqlite3
from datetime import date
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from shapely.geometry import Point, shape
from sklearn.cluster import DBSCAN
from streamlit_folium import st_folium

DB = "water_tests.db"

st.set_page_config(page_title="JalaAlert", page_icon="💧", layout="wide")

# -------------------------
# Local/offline storage
# -------------------------
def db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_type TEXT NOT NULL,
            result TEXT NOT NULL,
            test_date TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            notes TEXT DEFAULT '',
            synced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

conn = db()

def load_tests():
    return pd.read_sql_query("SELECT * FROM tests ORDER BY test_date DESC, id DESC", conn)

def add_test(test_type, result, test_date, lat, lon, notes):
    conn.execute(
        """INSERT INTO tests(test_type,result,test_date,latitude,longitude,notes,synced)
           VALUES(?,?,?,?,?,?,0)""",
        (test_type, result, str(test_date), lat, lon, notes)
    )
    conn.commit()

# -------------------------
# Helpers
# -------------------------
def normalize_result(x):
    s = str(x).strip().lower()
    if any(k in s for k in ["positive", "unsafe", "contaminated", "fail"]):
        return "Positive"
    if any(k in s for k in ["negative", "safe", "pass", "clear"]):
        return "Negative"
    return str(x).strip().title()

def find_col(df, names):
    low = {c.lower().strip(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    for c in df.columns:
        lc = c.lower().strip()
        if any(n in lc for n in names):
            return c
    return None

def load_uploaded_tests(upload):
    df = pd.read_csv(upload)
    lat = find_col(df, ["latitude", "lat"])
    lon = find_col(df, ["longitude", "lon", "lng"])
    result = find_col(df, ["result", "status", "test_result"])
    typ = find_col(df, ["test_type", "test type", "type"])
    dt = find_col(df, ["date", "test_date", "test date"])
    if not all([lat, lon, result, dt]):
        raise ValueError("Tests CSV needs latitude, longitude, result/status and date columns.")
    out = pd.DataFrame({
        "test_type": df[typ] if typ else "Water test",
        "result": df[result].map(normalize_result),
        "test_date": pd.to_datetime(df[dt], errors="coerce").dt.date.astype("string"),
        "latitude": pd.to_numeric(df[lat], errors="coerce"),
        "longitude": pd.to_numeric(df[lon], errors="coerce"),
    })
    out["notes"] = ""
    out = out.dropna(subset=["test_date", "latitude", "longitude"])
    return out

def load_rainfall(upload):
    df = pd.read_csv(upload)
    dt = find_col(df, ["date", "rainfall_date"])
    rain = find_col(df, ["rainfall", "rain_mm", "rain_mm_day", "mm"])
    if not dt or not rain:
        raise ValueError("Rainfall CSV needs date and rainfall/mm columns.")
    out = pd.DataFrame({
        "date": pd.to_datetime(df[dt], errors="coerce").dt.date.astype("string"),
        "rain_mm": pd.to_numeric(df[rain], errors="coerce")
    }).dropna()
    return out.groupby("date", as_index=False)["rain_mm"].sum()

def cluster_positive(df, radius_m=1000, min_samples=3):
    p = df[df["result"].map(normalize_result) == "Positive"].dropna(
        subset=["latitude", "longitude"]
    ).copy()
    if len(p) < min_samples:
        p["cluster"] = -1
        return p
    coords = np.radians(p[["latitude", "longitude"]].to_numpy())
    eps = radius_m / 6371000.0
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="haversine").fit_predict(coords)
    p["cluster"] = labels
    return p

def ward_for_point(lat, lon, geojson):
    if not geojson:
        return None
    pt = Point(float(lon), float(lat))
    for feat in geojson.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            if shape(geom).contains(pt):
                props = feat.get("properties", {})
                return props.get("ward") or props.get("name") or props.get("WARD") or "Unknown ward"
        except Exception:
            pass
    return None

# -------------------------
# Sidebar
# -------------------------
st.sidebar.title("💧 JalaAlert")
st.sidebar.caption("Household drinking-water contamination early warning")

tests_upload = st.sidebar.file_uploader("Household test CSV", type=["csv"])
rain_upload = st.sidebar.file_uploader("Rainfall CSV", type=["csv"])
boundary_upload = st.sidebar.file_uploader("Panchayat/Ward GeoJSON", type=["geojson", "json"])

radius = st.sidebar.slider("Cluster radius (m)", 100, 3000, 1000, 100)
min_samples = st.sidebar.slider("Minimum positive tests", 2, 10, 3)

# -------------------------
# Header
# -------------------------
st.title("💧 JalaAlert — Water Contamination Early Warning")
st.caption("Offline-first field logging • contamination clustering • rainfall context • ward-level response")

tab1, tab2, tab3, tab4 = st.tabs(["📍 Log Test", "🗺️ Map & Alerts", "🏘️ Ward Dashboard", "📦 Data"])

# -------------------------
# Tab 1: offline entry
# -------------------------
with tab1:
    st.subheader("Record a household / field-worker test")
    with st.form("test_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            test_type = st.selectbox("Test type", ["Bacterial / E. coli", "Chemical", "Turbidity", "Other"])
            result = st.selectbox("Result", ["Positive", "Negative", "Inconclusive"])
            test_date = st.date_input("Test date", value=date.today())
        with c2:
            lat = st.number_input("Latitude", value=10.000000, format="%.6f")
            lon = st.number_input("Longitude", value=76.300000, format="%.6f")
            notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("💾 Save locally")
        if submitted:
            add_test(test_type, result, test_date, lat, lon, notes)
            st.success("Saved locally. This record is available even without internet.")

    st.info("Demo idea: explain that the local SQLite database represents offline-first storage. A future sync service can upload unsynced rows when connectivity returns.")

# -------------------------
# Load data
# -------------------------
tests = load_tests()
if tests_upload:
    try:
        uploaded = load_uploaded_tests(tests_upload)
        tests = pd.concat([tests, uploaded], ignore_index=True)
        st.sidebar.success(f"Loaded {len(uploaded)} supplied test records.")
    except Exception as e:
        st.sidebar.error(str(e))

rain = pd.DataFrame(columns=["date", "rain_mm"])
if rain_upload:
    try:
        rain = load_rainfall(rain_upload)
    except Exception as e:
        st.sidebar.error(str(e))

geojson = None
if boundary_upload:
    try:
        geojson = json.load(boundary_upload)
    except Exception as e:
        st.sidebar.error(f"Boundary file error: {e}")

# Clean
if not tests.empty:
    tests["result"] = tests["result"].map(normalize_result)
    tests["test_date"] = pd.to_datetime(tests["test_date"], errors="coerce").dt.date
    tests["latitude"] = pd.to_numeric(tests["latitude"], errors="coerce")
    tests["longitude"] = pd.to_numeric(tests["longitude"], errors="coerce")
    tests = tests.dropna(subset=["latitude", "longitude", "test_date"])

# -------------------------
# Tab 2: map + alerts
# -------------------------
with tab2:
    st.subheader("Map-based early warning")
    if tests.empty:
        st.warning("Upload the organiser's test CSV or add a test in Log Test.")
    else:
        positives = cluster_positive(tests, radius, min_samples)
        clustered = positives[positives["cluster"] >= 0]
        alerts = []
        for cid, g in clustered.groupby("cluster"):
            alerts.append({
                "cluster": int(cid),
                "positive_tests": len(g),
                "lat": g["latitude"].mean(),
                "lon": g["longitude"].mean(),
                "latest_date": g["test_date"].max()
            })
        alerts_df = pd.DataFrame(alerts)

        # Rainfall join
        if not rain.empty:
            tests2 = tests.copy()
            tests2["date"] = tests2["test_date"].astype("string")
            tests2 = tests2.merge(rain, on="date", how="left")
            recent_rain = float(tests2["rain_mm"].fillna(0).sum())
        else:
            recent_rain = 0.0

        m = folium.Map(
            location=[tests["latitude"].mean(), tests["longitude"].mean()],
            zoom_start=12,
            control_scale=True
        )

        if geojson:
            folium.GeoJson(
                geojson,
                name="Ward boundaries",
                style_function=lambda x: {
                    "fillOpacity": 0.05,
                    "weight": 1
                }
            ).add_to(m)

        for _, r in tests.iterrows():
            is_pos = r["result"] == "Positive"
            folium.CircleMarker(
                [r["latitude"], r["longitude"]],
                radius=7 if is_pos else 5,
                popup=f"{r['test_type']} • {r['result']} • {r['test_date']}",
                tooltip=r["result"],
                fill=True,
                color="red" if is_pos else "green",
                fill_opacity=0.8
            ).add_to(m)

        for _, a in alerts_df.iterrows():
            folium.Circle(
                [a["lat"], a["lon"]],
                radius=radius,
                color="red",
                fill=False,
                weight=3,
                popup=f"ALERT CLUSTER: {a['positive_tests']} positive tests"
            ).add_to(m)

        st_folium(m, width=None, height=500, returned_objects=[])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total tests", len(tests))
        c2.metric("Positive tests", int((tests["result"] == "Positive").sum()))
        c3.metric("Alert clusters", len(alerts_df))
        c4.metric("Rainfall loaded", f"{recent_rain:.1f} mm")

        if len(alerts_df):
            st.error("⚠️ Potential contamination cluster detected.")
            st.write("Suggested response: notify the local body, prioritize confirmatory testing, and display the affected area on the ward dashboard.")
        else:
            st.success("No configurable cluster threshold crossed in the current dataset.")

        st.warning(
            "Important: this prototype does NOT declare water medically safe or unsafe. "
            "Alerts indicate patterns in reported tests and should be confirmed through authorised testing and approved public-health guidance."
        )

# -------------------------
# Tab 3: ward dashboard
# -------------------------
with tab3:
    st.subheader("Local-body / ward response view")
    if tests.empty:
        st.info("Add or upload test records first.")
    else:
        ward_rows = []
        for _, r in tests.iterrows():
            ward = ward_for_point(r["latitude"], r["longitude"], geojson)
            ward_rows.append(ward or "Ward data not supplied")
        t = tests.copy()
        t["ward"] = ward_rows

        summary = (
            t.assign(is_positive=t["result"].eq("Positive").astype(int))
             .groupby("ward")
             .agg(
                 tests=("id", "count"),
                 positive=("is_positive", "sum"),
                 latest_test=("test_date", "max")
             )
             .reset_index()
        )
        summary["status"] = np.where(summary["positive"] >= min_samples, "ATTENTION", "Monitor")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("Recommended response queue")
        attention = summary[summary["status"] == "ATTENTION"]
        if attention.empty:
            st.write("No ward has crossed the demo attention threshold.")
        else:
            for _, r in attention.iterrows():
                st.error(
                    f"**{r['ward']}** — {r['positive']} positive tests. "
                    f"Prioritise confirmatory testing and local-body review."
                )

# -------------------------
# Tab 4: data + sync concept
# -------------------------
with tab4:
    st.subheader("Offline-first data")
    st.write("Local records are stored in SQLite. Rows created by the field form start with synced = 0.")
    st.dataframe(tests, use_container_width=True, hide_index=True)
    st.caption("For the demo, present this as a local queue. A production version would sync unsynced rows to a shared server when connectivity returns.")

st.divider()
st.caption("JalaAlert • FutureBuild 2026 prototype • Pattern detection, not a medical diagnosis")
