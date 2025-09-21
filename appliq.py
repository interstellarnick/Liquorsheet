
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
    q = st.text_input("🔎 Search", key="q", placeholder="Brand, item, type, location…")


# ---------------------- Primary Category Selector ----------------------
# Top-level segmented control to choose which Category (tab) feeds the table
_cat_options = ["All"] + sorted([c for c in df.get("Category", pd.Series()).dropna().unique().tolist() if str(c).strip()])
default_idx = _cat_options.index("Whiskey") if "Whiskey" in _cat_options else 0
active_category = st.radio("Category", options=_cat_options, horizontal=True, index=default_idx, key="active_category")

st.caption(f"Data source: **{source or 'Unknown'}** • Edits save to local app storage (ephemeral on Streamlit Cloud). Use Export CSV for a durable copy.")

# ---- Clear filters button ----
if st.button('Show all / Clear filters'):
    # Reset search, category, location and advanced filters
    st.session_state['q'] = ''
    st.session_state['active_category'] = 'All'
    if 'sel_loc' in st.session_state:
        st.session_state['sel_loc'] = []
    for k in list(st.session_state.keys()):
        if str(k).startswith('adv_'):
            st.session_state[k] = []
    st.rerun()

# ---------------------- Filters ----------------------
left, right = st.columns([2,1])
with left:
    # Location filter (optional)
    locs = sorted(list(set([l for l in pd.concat([df.get("Location 1", pd.Series()), df.get("Location 2", pd.Series())], ignore_index=True).dropna().unique().tolist() if str(l).strip()])))
    sel_loc = st.multiselect("Location filter (optional)", options=locs, default=[], key="sel_loc")

with right:
    with st.expander("Advanced filters (optional)"):
        # Build per-column multiselects for key columns
        adv_filters = {}
        for _col in ["Brand","Type","Size","Location 1","Location 2"]:
            if _col in df.columns:
                opts = sorted([x for x in df[_col].dropna().astype(str).unique().tolist() if str(x).strip()])
                if opts:
                    adv_filters[_col] = st.multiselect(_col, options=opts, default=[], key=f"adv_{_col}")
# Apply search/filters
filtered = df.copy()
if active_category != "All":
    filtered = filtered[filtered["Category"] == active_category]
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
# Advanced filters
try:
    for _c, _vals in adv_filters.items():
        if _vals:
            filtered = filtered[filtered[_c].isin(_vals)]
except Exception:
    pass
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


# ---------------------- Chart Builder ----------------------
st.markdown("### Chart Builder")

# Candidate categorical columns
_cats = [c for c in ["Category","Brand","Type","Size","Location 1","Location 2"] if c in filtered.columns]
if not _cats:
    st.info("No categorical columns available for charting.")
else:
    colA, colB, colC, colD = st.columns([1.2,1.2,1,1])
    with colA:
        x_col = st.selectbox("X axis", options=_cats, index=0)
    with colB:
        group_col = st.selectbox("Group (optional)", options=["None"] + _cats, index=0)
    with colC:
        metric = st.selectbox("Metric", options=["Rows (items)","Total bottles (Full+Partial)"], index=1)
    with colD:
        top_n = st.slider("Top N", min_value=5, max_value=50, value=20, step=5)

    chart_df = filtered.copy()
    # Build a 'Location' helper if user selected one of the two location cols as X or Group
    # (We keep them separate, but nothing special needed unless we wanted to merge)

    # Aggregate
    if metric.startswith("Rows"):
        agg = {"_val":"size"}
        chart_df["_val"] = 1
    else:
        # Total bottles = Full + Partial
        chart_df["_val"] = chart_df.get("Qty Full", 0) + chart_df.get("Qty Partial", 0)
        agg = {"_val":"sum"}

    if group_col == "None":
        gb = chart_df.groupby(x_col, dropna=False)["_val"].agg(agg["_val"]).reset_index(name="Value")
        gb = gb.sort_values("Value", ascending=False).head(top_n)
        fig = px.bar(gb, x=x_col, y="Value", title=f"{metric} by {x_col}")
    else:
        gb = chart_df.groupby([x_col, group_col], dropna=False)["_val"].agg(agg["_val"]).reset_index(name="Value")
        # limit to Top N by main X
        top_keys = gb.groupby(x_col)["Value"].sum().sort_values(ascending=False).head(top_n).index
        gb = gb[gb[x_col].isin(top_keys)]
        fig = px.bar(gb, x=x_col, y="Value", color=group_col, barmode="group", title=f"{metric} by {x_col} grouped by {group_col}")

    st.plotly_chart(fig, use_container_width=True)

# ---------------------- Editable Ratings ----------------------
st.markdown("### Edit Ratings")

# Helper to render clickable stars and return updated value
def render_star_row(row_id: int, current: int) -> int:
    current = int(current) if pd.notna(current) else 0
    cols = st.columns(5)
    clicked_value = None
    for i in range(1, 6):
        label = "★" if i <= current else "☆"
        if cols[i-1].button(label, key=f"star_{row_id}_{i}"):
            clicked_value = i
    return clicked_value if clicked_value is not None else current

if "Rating" in filtered.columns:
    edit_df = filtered[["Category","Brand","Item","Type","Size","Rating"]].copy()
else:
    edit_df = pd.DataFrame(columns=["Category","Brand","Item","Type","Size","Rating"])

new_ratings = {}
for idx, row in edit_df.reset_index().iterrows():
    ridx = int(row["index"])
    c1, c2, c3, c4, c5 = st.columns([2,2,2,2,3])
    with c1: st.write(row.get("Category",""))
    with c2: st.write(row.get("Brand",""))
    with c3: st.write(row.get("Item",""))
    with c4: st.write(row.get("Type",""))
    with c5:
        current = int(row.get("Rating", 0)) if pd.notna(row.get("Rating", 0)) else 0
        updated = render_star_row(ridx, current)
        # Show numeric hint under stars (optional)
        st.caption(f"{updated}/5")
        new_ratings[ridx] = int(updated)

if st.button("💾 Save ratings (session & file)"):
    for ridx, val in new_ratings.items():
        if "Rating" in df.columns:
            df.loc[ridx, "Rating"] = val
    Path(DATA_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_CSV, index=False)
    st.success("Ratings saved. (Note: on Streamlit Cloud this persists until the app restarts.)")
    st.cache_data.clear()
    st.rerun()

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
