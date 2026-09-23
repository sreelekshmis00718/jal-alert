
# JalaAlert — 2–3 hour hackathon MVP

## What this prototype covers
- Offline-first household/field-worker test logging using local SQLite.
- CSV ingestion for the organiser's supplied household test dataset.
- Map of positive/negative observations.
- Configurable contamination-cluster detection using DBSCAN + a radius in metres.
- Rainfall CSV integration.
- Panchayat/ward GeoJSON overlay and point-in-ward assignment.
- Ward-level attention dashboard.
- Explicit public-health safety boundary: it does not declare water medically safe/unsafe.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Expected CSV formats

### Tests CSV
Column names can vary slightly. The app looks for:
- latitude / lat
- longitude / lon / lng
- result / status / test_result
- date / test_date
- optional: test_type / type

### Rainfall CSV
- date
- rainfall / rain_mm / rain_mm_day / mm

### Boundary
GeoJSON FeatureCollection. Ward name can be in a property called:
- ward
- name
- WARD

## 2–3 hour demo plan
1. 0:00–0:20 — install dependencies and run app.
2. 0:20–0:50 — load organiser CSV + GeoJSON + rainfall.
3. 0:50–1:30 — tune cluster radius/minimum positives to match supplied scenario.
4. 1:30–2:00 — polish labels, add screenshots/logo, rehearse.
5. 2:00–2:30 — optional time-series/confidence scoring.

## Pitch in one sentence
“JalaAlert turns scattered household water-test observations into an offline-first, map-based early-warning system that combines test clusters with rainfall and gives local bodies a ward-level response view.”

## Important
The organiser's brief says the prototype must not make a medical certainty claim. Keep wording like:
“Potential contamination pattern detected — confirm through authorised testing and approved public-health guidance.”
