
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path
import tempfile
import io

st.set_page_config(page_title="Liquor Inventory", layout="wide")

def _format_abv(val):
    """Return a clean percent string like '40%' from varied inputs.
    Rules: numbers <= 1 are treated as fractions (e.g., 0.4 -> 40%),
    numbers > 1 are treated as percents (e.g., 40 -> 40%). Strings with '%' keep numeric part.
    """
    import math, re
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return ""
    # Extract number possibly with % sign
    m = re.search(r"-?\d+(?:[\.,]\d+)?", s.replace(',', '.'))
    if not m:
        return s  # fallback, show raw
    num = float(m.group(0))
    # If original string contains '%', assume already percent
    if '%' in s:
        pct = num
    else:
        pct = num*100 if 0 <= num <= 1 else num
    # Clean formatting: drop .0
    if abs(pct - round(pct)) < 1e-9:
        return f"{int(round(pct))}%"
    else:
        return f"{pct:.1f}%"


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


from pathlib import Path
import pandas as pd
import numpy as np
import tempfile, glob

# ---------- FIND + READ ----------
def _find_data():
    # Preferred exact paths
    candidates = [
        ("csv", "data/liquor_inventory.csv"),
        ("xlsx","data/liquor_inventory.xlsx"),
        # common alternates
        ("xlsx","Liquor Inventory.xlsx"),
        ("xlsx","liquor_inventory.xlsx"),
    ]
    for kind, pth in candidates:
        if Path(pth).exists():
            return kind, pth

    # Any CSV/XLSX in data/ then anywhere in repo
    for pattern in ["data/*.csv", "data/*.xlsx", "*.csv", "*.xlsx", "**/*.csv", "**/*.xlsx"]:
        files = sorted(glob.glob(pattern, recursive=True))
        if files:
            csvs  = [f for f in files if f.lower().endswith(".csv")]
            xlsxs = [f for f in files if f.lower().endswith((".xlsx",".xls"))]
            if csvs:
                return "csv", csvs[0]
            if xlsxs:
                return "xlsx", xlsxs[0]
    return None, None

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

@st.cache_data(show_spinner=False)
def _read_csv_safely(path: str, cache_key: str) -> pd.DataFrame:
    pth = Path(path)
    if not pth.exists():
        return pd.DataFrame()
    return pd.read_csv(pth)

def _cache_key_for(path: str) -> str:
    pth = Path(path)
    if pth.exists():
        s = pth.stat()
        return f"{pth.resolve()}::{s.st_mtime_ns}::{s.st_size}"
    return "missing"

# ---------- Load flow ----------
kind, path = _find_data()
df = pd.DataFrame()
source = None

if kind == "csv":
    df = _read_csv_safely(path, _cache_key_for(path)).copy()
    source = f"Repo CSV: {path}"
elif kind == "xlsx":
    df = _excel_to_df(path)
    source = f"Repo Excel: {path}"
    # optional: persist to canonical CSV for faster future loads
    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/liquor_inventory.csv", index=False)

if df.empty:
    st.warning("No bundled data found. Upload a .csv or .xlsx to get started.")
    up = st.file_uploader("Upload inventory (.csv or .xlsx)", type=["csv","xlsx"])
    if up is not None:
        if up.name.lower().endswith(".csv"):
            df = pd.read_csv(up); source = f"Uploaded CSV: {up.name}"
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.write(up.getvalue()); tmp.flush()
            df = _excel_to_df(tmp.name); source = f"Uploaded Excel: {up.name}"
    if df.empty:
        st.stop()

# Final normalization
for col in ["Location 1","Location 2"]:
    if col not in df.columns: df[col] = ""
    df[col] = df[col].fillna("").astype(str).str.strip()

st.caption(f"Data source: **{source or 'Unknown'}**")
with st.expander("Debug: files the app can see", expanded=False):
    st.write("Found kind/path:", kind, path)
    import os
    st.write("Repo root files:", os.listdir("."))
    st.write("data/ files:", os.listdir("data") if Path("data").exists() else "no data/ dir")
with st.expander("Debug: files the app can see", expanded=False):
    st.write("Found kind/path:", kind, path)
    st.write("Repo root files:", os.listdir("."))
    st.write("data/ files:", os.listdir("data") if Path("data").exists() else "no data/ dir")

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
st.dataframe(by_loc.sort_values("Total", ascending=False), width='stretch')

st.divider()


# ---------------------- Categories Overview ----------------------
st.markdown("### Categories Overview")

if "Category" in df.columns and len(df):
    # Summary table: Items (rows) and Bottles (Full+Partial) by Category
    summary = df.assign(_bottles=df.get("Qty Full", 0) + df.get("Qty Partial", 0)) \
                .groupby("Category").agg(Items=("Item","count"), Bottles=("_bottles","sum")) \
                .reset_index().sort_values("Items", ascending=False)
    c1, c2 = st.columns([1.2,1])
    with c1:
        st.dataframe(summary, width='stretch')
    with c2:
        fig_p = px.pie(summary, values="Items", names="Category", title="Items by Category", hole=0.35)
        st.plotly_chart(fig_p, width='stretch')
else:
    st.info("No category data available.")


# ---------------------- Items Available ----------------------
st.markdown("## Items Available")

# Build the view with requested columns
items_df = filtered.copy()
# Ensure columns exist
for _col in ["Brand","Item","ABV","Size","Rating"]:
    if _col not in items_df.columns:
        items_df[_col] = "" if _col != "Rating" else 0
items_df["Brand"] = items_df["Brand"].astype(str).str.strip()
items_df["Item"] = items_df["Item"].astype(str).str.strip()
items_df["ABV"] = items_df["ABV"].astype(str).str.strip()  # raw
items_df["ABV_fmt"] = items_df["ABV"].apply(_format_abv)
items_df["Size"] = items_df["Size"].astype(str).str.strip()
items_df["Rating"] = pd.to_numeric(items_df["Rating"], errors="coerce").fillna(0).clip(0,5).astype(int)

# Header row
hc1, hc2, hc3, hc4, hc5 = st.columns([2,3,1.2,1.2,2.2])
with hc1: st.markdown("**Liquor Brand**")
with hc2: st.markdown("**Item**")
with hc3: st.markdown("**% Alcohol**")
with hc4: st.markdown("**Size**")
with hc5: st.markdown("**Rating**")

# Interactive star control per row (⭐ for selected, ☆ for empty)
pending_updates = {}
for ridx, row in items_df.reset_index().iterrows():
    src_idx = int(row["index"])
    c1, c2, c3, c4, c5 = st.columns([2,3,1.2,1.2,2.2])
    with c1: st.write(row["Brand"])
    with c2: st.write(row["Item"])
    with c3: st.write(_format_abv(row["ABV"]))
    with c4: st.write(row["Size"])
    with c5:
        current = int(row["Rating"]) if pd.notna(row["Rating"]) else 0
        scols = st.columns(5)
        new_val = current
        for i in range(1, 6):
            label = "⭐" if i <= current else "☆"
            if scols[i-1].button(label, key=f"rate_star_{src_idx}_{i}"):
                new_val = i
        if new_val != current:
            pending_updates[src_idx] = new_val
        st.caption(f"{new_val}/5")

# Apply saves
if st.button("💾 Save ratings (session & file)"):
    if "Rating" in df.columns:
        for idx0, val0 in pending_updates.items():
            df.loc[idx0, "Rating"] = int(val0)
        Path(DATA_CSV).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA_CSV, index=False)
        st.success("Ratings saved. (Note: on Streamlit Cloud this persists until the app restarts.)")
        st.cache_data.clear()
        st.rerun()
    else:
        st.warning("No 'Rating' column in data; cannot save.")

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
