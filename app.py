import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path
import time

st.set_page_config(page_title="Liquor Inventory", layout="wide")

DATA_XLSX = "data/liquor_inventory.xlsx"
DATA_CSV  = "data/liquor_inventory.csv"

@st.cache_data(show_spinner=False)
def load_inventory(csv_path: str, cache_key: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)

def get_cache_key(path: str) -> str:
    p = Path(path)
    if p.exists():
        s = p.stat()
        return f"{p.resolve()}::{s.st_mtime_ns}::{s.st_size}"
    return "missing"

def normalize_locations(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Location 1", "Location 2"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df

csv_key = get_cache_key(DATA_CSV)
df = load_inventory(DATA_CSV, csv_key).copy()
df = normalize_locations(df)

colLogo, colTitle, colSearch = st.columns([0.5, 2.5, 1])
with colLogo:
    st.markdown("### 🥃")
with colTitle:
    st.markdown("## Liquor Inventory")
with colSearch:
    q = st.text_input("🔎 Search", placeholder="Brand, item, type, location...")

left, right = st.columns([2,1])
with left:
    cats = ["All"] + sorted([c for c in df["Category"].dropna().unique().tolist() if c])
    sel_cat = st.selectbox("Category", options=cats, index=0)
    locs = sorted(list(set([l for l in pd.concat([df["Location 1"], df["Location 2"]], ignore_index=True).dropna().unique().tolist() if str(l).strip()])))
    sel_loc = st.multiselect("Location filter (optional)", options=locs, default=[])

filtered = df.copy()
if sel_cat != "All":
    filtered = filtered[filtered["Category"] == sel_cat]
if q:
    qq = q.lower().strip()
    search_cols = ["Brand","Item","Type","Size","Category","Location 1","Location 2"]
    mask = pd.Series(False, index=filtered.index)
    for c in search_cols:
        if c in filtered.columns:
            mask |= filtered[c].astype(str).str.lower().str_contains(qq, regex=False, na=False)
    filtered = filtered[mask]
if sel_loc:
    mask_loc = filtered["Location 1"].isin(sel_loc) | filtered["Location 2"].isin(sel_loc)
    filtered = filtered[mask_loc]

total_full = int(filtered["Qty Full"].sum())
total_partial = int(filtered["Qty Partial"].sum())
total_bottles = total_full + total_partial
c1, c2, c3 = st.columns(3)
with c1: st.metric("Total bottles", f"{total_bottles:,}")
with c2: st.metric("Full bottles", f"{total_full:,}")
with c3: st.metric("Partial bottles", f"{total_partial:,}")

loc_counts = (
    pd.concat([
        filtered[["Location 1","Qty Full","Qty Partial"]].rename(columns={"Location 1":"Location"}),
        filtered[["Location 2","Qty Full","Qty Partial"]].rename(columns={"Location 2":"Location"}),
    ], ignore_index=True)
    .assign(Location=lambda d: d["Location"].fillna("").astype(str).str.strip())
)
loc_counts = loc_counts[loc_counts["Location"] != ""]
by_loc = loc_counts.groupby("Location").agg(Full=("Qty Full","sum"), Partial=("Qty Partial","sum"))
by_loc["Total"] = by_loc["Full"] + by_loc["Partial"]
st.dataframe(by_loc.sort_values("Total", ascending=False), use_container_width=True)

st.divider()

lcol, rcol = st.columns(2)
with lcol:
    by_cat = filtered.groupby("Category").size().reset_index(name="Count")
    if not by_cat.empty:
        fig1 = px.bar(by_cat.sort_values("Count", ascending=False), x="Category", y="Count", title="Bottles by Category")
        st.plotly_chart(fig1, use_container_width=True)
with rcol:
    by_loc2 = by_loc.reset_index()
    if not by_loc2.empty:
        fig2 = px.bar(by_loc2, x="Location", y="Total", title="Bottles by Location")
        st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.markdown("### Edit Ratings (coming in this minimal fallback if needed)")
