
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path
import tempfile
import io

st.set_page_config(page_title="Liquor Inventory", layout="wide")

DATA_CSV  = "data/liquor_inventory.csv"
DATA_XLSX = "data/liquor_inventory.xlsx"

# ---------------------- Utilities ----------------------
def _cache_key_for(path: str) -> str:
    p = Path(path)
    if p.exists():
        s = p.stat()
        return f"{p.resolve()}::{s.st_mtime_ns}::{s.st_size}"
    return "missing"

@st.cache_data(show_spinner=False)
def _read_csv_safely(path: str, cache_key: str) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    return pd.read_csv(path)

def _excel_to_df(xlsx_path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(xlsx_path)
    frames = []
    for sh in xls.sheet_names:
        raw = pd.read_excel(xlsx_path, sheet_name=sh).dropna(how="all")

        def pick(names):
            for n in names:
                if n in raw.columns and not raw[n].dropna().empty:
                    return raw[n]
                for c in raw.columns:
                    cstr = str(c)
                    if cstr == n or cstr.startswith(n + "."):
                        if not raw[c].dropna().empty:
                            return raw[c]
            return pd.Series([np.nan] * len(raw))

        std = pd.DataFrame({
            "Brand":       pick(["Liquor Brand","Brand","brand"]),
            "Item":        pick(["Item","Name","Product"]),
            "Type":        pick(["Type","Category"]),
            "ABV":         pick(["% Alcohol","ABV"]),
            "Size":        pick(["Size","Volume"]),
            "Location 1":  pick(["Location 1","Location1","Location"]),
            "Qty Full":    pick(["Quanity Full","Quantity Full"]),
            "Qty Partial": pick(["Quanity Partial ","Quanity Partial","Quantity Partial","Quantity Partial "]),
            "Location 2":  pick(["Location 2","Location2"]),
            "Rating":      pick(["Rating"]),
        })
        std["Category"] = sh
        frames.append(std)

    df = pd.concat(frames, ignore_index=True)

    for c in ["Qty Full","Qty Partial"]:
        if c not in df.columns: df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    if "Rating" not in df.columns: df["Rating"] = 0
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce").fillna(0).clip(0,5).astype(int)
    for c in ["Brand","Item","Type","Size","Location 1","Location 2","Category"]:
        if c not in df.columns: df[c] = ""
        df[c] = df[c].astype(str).replace({"nan":""}).str.strip()
    return df

def _normalize_locations(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Location 1","Location 2"]:
        if col not in df.columns: df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df

# ---------------------- Load flow ----------------------
df = pd.DataFrame()
source = None

# Try CSV, then Excel, then upload
df = _read_csv_safely(DATA_CSV, _cache_key_for(DATA_CSV)).copy()
if not df.empty:
    source = f"Repo CSV: {DATA_CSV}"
elif Path(DATA_XLSX).exists():
    df = _excel_to_df(DATA_XLSX)
    source = f"Repo Excel: {DATA_XLSX}"
    Path(DATA_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_CSV, index=False)

if df.empty:
    st.warning("No bundled CSV/XLSX found. Upload a file to get started.")
    up = st.file_uploader("Upload inventory (.csv or .xlsx)", type=["csv","xlsx"])
    if up is not None:
        if up.name.lower().endswith(".csv"):
            df = pd.read_csv(up)
            source = f"Uploaded CSV: {up.name}"
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.write(up.getvalue()); tmp.flush()
            df = _excel_to_df(tmp.name)
            source = f"Uploaded Excel: {up.name}"
    if df.empty:
        st.stop()

df = _normalize_locations(df)

# ---------------------- Header / Search ----------------------
st.markdown(
    """
    <style>
      @media (max-width: 600px) {
        .kpi-value { font-size: 16px !important; }
        .kpi-label { font-size: 10px !important; }
      }
    </style>
    """, unsafe_allow_html=True
)

col1, col2, col3 = st.columns([0.6, 2.4, 1])
with col1:
    st.markdown("### 🥃")
with col2:
    st.markdown("## Liquor Inventory")
with col3:
    q = st.text_input("🔎 Search", placeholder="Brand, item, type, location…")

st.caption(f"Data source: **{source or 'Unknown'}** • Edits save to local app storage (ephemeral on Streamlit Cloud). Use Export CSV for a durable copy.")

# ---------------------- Filters ----------------------
left, right = st.columns([2,1])
with left:
    cats = ["All"] + sorted([c for c in df.get("Category", pd.Series()).dropna().unique().tolist() if str(c).strip()])
    sel_cat = st.selectbox("Category", options=cats, index=0)
    locs = sorted(list(set([l for l in pd.concat([df.get('Location 1', pd.Series()), df.get('Location 2', pd.Series())], ignore_index=True).dropna().unique().tolist() if str(l).strip()])))
    sel_loc = st.multiselect("Location filter (optional)", options=locs, default=[])

# Apply search/filters
filtered = df.copy()
if sel_cat != "All":
    filtered = filtered[filtered["Category"] == sel_cat]
if q:
    qq = q.lower().strip()
    search_cols = ["Brand","Item","Type","Size","Category","Location 1","Location 2"]
    mask = pd.Series(False, index=filtered.index)
    for c in search_cols:
        if c in filtered.columns:
            mask |= filtered[c].astype(str).str.lower().str.contains(qq, na=False)
    filtered = filtered[mask]
if sel_loc:
    mask_loc = filtered["Location 1"].isin(sel_loc) | filtered["Location 2"].isin(sel_loc)
    filtered = filtered[mask_loc]

# ---------------------- Callouts ----------------------
total_full = int(filtered.get("Qty Full", pd.Series(dtype=int)).sum())
total_partial = int(filtered.get("Qty Partial", pd.Series(dtype=int)).sum())
total_bottles = total_full + total_partial

k1, k2, k3 = st.columns(3)
with k1: st.metric("Total bottles", f"{total_bottles:,}")
with k2: st.metric("Full bottles", f"{total_full:,}")
with k3: st.metric("Partial bottles", f"{total_partial:,}")

# By location table
loc_counts = pd.concat([
    filtered[["Location 1","Qty Full","Qty Partial"]].rename(columns={"Location 1":"Location"}) if "Location 1" in filtered.columns else pd.DataFrame(columns=["Location","Qty Full","Qty Partial"]),
    filtered[["Location 2","Qty Full","Qty Partial"]].rename(columns={"Location 2":"Location"}) if "Location 2" in filtered.columns else pd.DataFrame(columns=["Location","Qty Full","Qty Partial"]),
], ignore_index=True)
loc_counts["Location"] = loc_counts.get("Location", pd.Series()).fillna("").astype(str).str.strip()
loc_counts = loc_counts[loc_counts["Location"] != ""]
by_loc = loc_counts.groupby("Location").agg(Full=("Qty Full","sum"), Partial=("Qty Partial","sum"))
by_loc["Total"] = by_loc["Full"] + by_loc["Partial"]
st.dataframe(by_loc.sort_values("Total", ascending=False), use_container_width=True)

st.divider()

# ---------------------- Charts ----------------------
c_left, c_right = st.columns(2)

with c_left:
    if "Category" in filtered.columns and len(filtered):
        by_cat = filtered.groupby("Category").size().reset_index(name="Count")
        fig1 = px.bar(by_cat.sort_values("Count", ascending=False), x="Category", y="Count", title="Bottles by Category")
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("No data for category chart")

with c_right:
    if not by_loc.empty:
        fig2 = px.bar(by_loc.reset_index(), x="Location", y="Total", title="Bottles by Location")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No data for location chart")

st.divider()

# ---------------------- Editable Ratings ----------------------
st.markdown("### Edit Ratings")
edit_df = filtered[["Category","Brand","Item","Type","Size","Rating"]].copy() if "Rating" in filtered.columns else pd.DataFrame(columns=["Category","Brand","Item","Type","Size","Rating"])

new_ratings = {}
for idx, row in edit_df.reset_index().iterrows():
    ridx = int(row["index"])
    cols = st.columns([2,2,2,2,1,2])
    with cols[0]: st.write(row.get("Category",""))
    with cols[1]: st.write(row.get("Brand",""))
    with cols[2]: st.write(row.get("Item",""))
    with cols[3]: st.write(row.get("Type",""))
    with cols[4]: st.write(str(row.get("Size","")))
    with cols[5]:
        current = int(row.get("Rating", 0)) if pd.notna(row.get("Rating", 0)) else 0
        r = st.radio(
            label=f"Rating for {row.get('Item','')}",
            options=[0,1,2,3,4,5],
            index=current,
            key=f"rate_{ridx}",
            format_func=lambda x: "★"*x + "☆"*(5-x),
            horizontal=True
        )
        new_ratings[ridx] = int(r)

if st.button("💾 Save ratings (session & file)"):
    for ridx, val in new_ratings.items():
        if "Rating" in df.columns:
            df.loc[ridx, "Rating"] = val
    # Persist to CSV (ephemeral on Cloud)
    Path(DATA_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_CSV, index=False)
    st.success("Ratings saved. (Note: on Streamlit Cloud this persists until the app restarts.)")
    st.cache_data.clear()
    st.rerun()

st.divider()

# ---------------------- Add New Bottle ----------------------
st.markdown("### Add a New Bottle")
with st.form("add_bottle"):
    cA, cB, cC = st.columns(3)
    with cA:
        n_cat = st.selectbox("Category", options=sorted([c for c in df.get("Category", pd.Series()).dropna().unique()]) if "Category" in df.columns else [], index=0 if "Category" in df.columns and df["Category"].dropna().size else 0)
        n_brand = st.text_input("Brand")
        n_item = st.text_input("Item")
    with cB:
        n_type = st.text_input("Type")
        n_size = st.text_input("Size (e.g., 750ml)")
        n_abv = st.text_input("ABV (%)", value="")
    with cC:
        n_loc1 = st.text_input("Location 1")
        n_loc2 = st.text_input("Location 2", value="")
        n_rating = st.slider("Rating", 0, 5, 0)
    n_full = st.number_input("Quantity Full", min_value=0, value=0, step=1)
    n_partial = st.number_input("Quantity Partial", min_value=0, value=0, step=1)

    submitted = st.form_submit_button("➕ Add bottle")
    if submitted:
        new_row = {
            "Brand": n_brand.strip(),
            "Item": n_item.strip(),
            "Type": n_type.strip(),
            "ABV": n_abv.strip(),
            "Size": n_size.strip(),
            "Location 1": n_loc1.strip(),
            "Qty Full": int(n_full),
            "Qty Partial": int(n_partial),
            "Location 2": n_loc2.strip(),
            "Rating": int(n_rating),
            "Category": n_cat if "Category" in df.columns else "",
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        Path(DATA_CSV).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA_CSV, index=False)
        st.success(f"Added {n_brand} {n_item} to inventory.")
        st.cache_data.clear()
        st.rerun()

st.caption("Use **⬇️ Export** as your durable backup.")
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Export current inventory CSV", csv_bytes, file_name="liquor_inventory.csv", mime="text/csv")
