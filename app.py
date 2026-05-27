import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path


# ============================================================
# App configuration
# ============================================================

st.set_page_config(
    page_title="DF Finder",
    page_icon="🌲",
    layout="wide"
)


# ============================================================
# Data loading
# ============================================================

@st.cache_data
def load_data():
    data_dir = Path("data")
    excel_path = data_dir / "df_master_extraction_cleaned.xlsx"

    df_values = pd.read_excel(
        excel_path,
        sheet_name="df_values"
    )

    studies = pd.read_excel(
        excel_path,
        sheet_name="studies"
    )

    df_values["df_value"] = pd.to_numeric(df_values["df_value"], errors="coerce")

    return df_values, studies


df_values, studies = load_data()


# ============================================================
# Helper functions
# ============================================================

def unique_options(df, column):
    return sorted(df[column].dropna().astype(str).unique())


def apply_filters(df, product_group, end_use, geography):
    filtered = df.copy()

    if product_group != "All":
        filtered = filtered[filtered["product_group"] == product_group]

    if end_use != "All":
        filtered = filtered[filtered["end_use"] == end_use]

    if geography != "All":
        filtered = filtered[filtered["geography"] == geography]

    return filtered


def calculate_recommendation(filtered, mode):
    values = filtered["df_value"].dropna()

    if values.empty:
        return None

    if mode == "Conservative":
        recommended = values.quantile(0.25)
    elif mode == "Optimistic":
        recommended = values.quantile(0.75)
    else:
        recommended = values.median()

    return {
        "recommended": round(recommended, 2),
        "min": round(values.min(), 2),
        "max": round(values.max(), 2),
        "median": round(values.median(), 2),
        "n_values": len(values),
        "n_studies": filtered["study_id"].nunique()
    }


def confidence_label(n_values, n_studies):
    if n_values >= 10 and n_studies >= 5:
        return "High"
    elif n_values >= 4 and n_studies >= 2:
        return "Medium"
    elif n_values >= 1:
        return "Low"
    else:
        return "No data"


# ============================================================
# Header
# ============================================================

st.title("🌲 DF Finder")
st.caption(
    "A decision-support prototype for exploring displacement factors "
    "for wood-based products."
)

st.markdown("---")


# ============================================================
# Sidebar filters
# ============================================================

st.sidebar.header("Select product context")

product_group = st.sidebar.selectbox(
    "Product group",
    ["All"] + unique_options(df_values, "product_group")
)

end_use = st.sidebar.selectbox(
    "End use",
    ["All"] + unique_options(df_values, "end_use")
)

geography = st.sidebar.selectbox(
    "Geography",
    ["All"] + unique_options(df_values, "geography")
)

mode = st.sidebar.radio(
    "Recommendation style",
    ["Conservative", "Central", "Optimistic"],
    index=1
)


# ============================================================
# Filter data
# ============================================================

filtered = apply_filters(df_values, product_group, end_use, geography)
recommendation = calculate_recommendation(filtered, mode)


# ============================================================
# Main result panel
# ============================================================

st.subheader("Recommended displacement factor")

if recommendation is None:
    st.warning("No matching DF values found for the selected filters.")
    st.stop()

confidence = confidence_label(
    recommendation["n_values"],
    recommendation["n_studies"]
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Recommended DF", recommendation["recommended"])
col2.metric("Range", f"{recommendation['min']} – {recommendation['max']}")
col3.metric("DF observations", recommendation["n_values"])
col4.metric("Confidence", confidence)

st.info(
    "This value represents displacement potential based on the selected evidence. "
    "It should not be interpreted as guaranteed realized substitution."
)


# ============================================================
# Plot
# ============================================================

st.subheader("Distribution of matching DF values")

fig = px.box(
    filtered,
    y="df_value",
    points="all",
    hover_data=[
        "study_id",
        "wood_product",
        "geography",
        "end_use"
    ],
    title="DF value distribution"
)

st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Evidence table
# ============================================================

st.subheader("Supporting DF observations")

display_cols = [
    "df_id",
    "study_id",
    "product_group",
    "wood_product",
    "alternative_product",
    "end_use",
    "geography",
    "df_value",
    "notes"
]

available_cols = [c for c in display_cols if c in filtered.columns]

st.dataframe(
    filtered[available_cols].sort_values("df_value"),
    use_container_width=True
)


# ============================================================
# Study metadata
# ============================================================

st.subheader("Supporting studies")

study_ids = filtered["study_id"].dropna().unique()
supporting_studies = studies[studies["study_id"].isin(study_ids)]

study_cols = [
    "study_id",
    "authors",
    "year",
    "title",
    "journal",
    "doi",
    "country_region",
    "notes"
]

available_study_cols = [c for c in study_cols if c in supporting_studies.columns]

st.dataframe(
    supporting_studies[available_study_cols],
    use_container_width=True
)
