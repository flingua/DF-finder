
# DF Finder v0.4 — Guided decision-tree prototype

import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="DF Finder", page_icon="🌲", layout="wide")

@st.cache_data
def load_data():
    data_dir = Path("data")
    excel_path = data_dir / "df_master_extraction_cleaned.xlsx"

    df_values = pd.read_excel(excel_path, sheet_name="df_values")
    studies = pd.read_excel(excel_path, sheet_name="studies")

    df_values["df_value"] = pd.to_numeric(df_values["df_value"], errors="coerce")

    return df_values, studies

df_values, studies = load_data()

PRODUCT_SYSTEM_MAP = {
    "Solid wood products": "Construction and buildings",
    "Housing": "Construction and buildings",
    "Paper/Fibre products": "Packaging and fibre products",
    "Energy": "Bioenergy",
    "Textiles": "Textiles and biomaterials",
    "Combined wood-based products": "Mixed / general wood products",
    "Roundwood": "Mixed / general wood products",
}

if "product_group" in df_values.columns:
    df_values["product_system"] = (
        df_values["product_group"]
        .map(PRODUCT_SYSTEM_MAP)
        .fillna("Mixed / general wood products")
    )
else:
    df_values["product_system"] = "Mixed / general wood products"

def classify_application(text):
    text = str(text).lower()

    if any(x in text for x in ["house", "building", "frame"]):
        return "Whole building or structural frame"

    if any(x in text for x in ["door", "floor", "window", "decking", "siding"]):
        return "Building component"

    if any(x in text for x in ["packaging", "carton", "bag", "box"]):
        return "Packaging"

    if any(x in text for x in ["heat", "bioenergy", "pellet", "electricity"]):
        return "Energy substitution"

    if "furniture" in text:
        return "Furniture"

    return "General / mixed"

if "wood_product" in df_values.columns:
    df_values["application_family"] = df_values["wood_product"].apply(classify_application)
else:
    df_values["application_family"] = "General / mixed"

st.sidebar.title("🌲 DF Finder")

product_system = st.sidebar.selectbox(
    "What kind of wood product or use are you looking at?",
    sorted(df_values["product_system"].dropna().unique())
)

available_apps = sorted(
    df_values.loc[
        df_values["product_system"] == product_system,
        "application_family"
    ].dropna().unique()
)

application = st.sidebar.selectbox(
    "Which option is closest to your case?",
    available_apps
)

counterfactual = st.sidebar.selectbox(
    "What is it mainly replacing?",
    [
        "Concrete",
        "Steel",
        "Plastic",
        "Fossil fuels",
        "Mixed materials",
        "Not specified"
    ]
)

geography = st.sidebar.selectbox(
    "Which region is most relevant?",
    [
        "Sweden",
        "Nordic",
        "Europe",
        "North America",
        "Global"
    ]
)

mode = st.sidebar.radio(
    "How cautious should the estimate be?",
    ["Conservative", "Central", "Optimistic"],
    index=1
)

filtered = df_values[
    (df_values["product_system"] == product_system) &
    (df_values["application_family"] == application)
].copy()

evidence_level = "Direct evidence"

if filtered.empty:
    filtered = df_values[
        df_values["product_system"] == product_system
    ].copy()

    evidence_level = "Closest available evidence from the same product family"

if filtered.empty:

    fallback_values = {
        "Conservative": 0.8,
        "Central": 1.2,
        "Optimistic": 1.6
    }

    st.warning(
        "No matching studies were found. Using broad mixed-product fallback values."
    )

    st.metric(
        "Suggested fallback DF",
        fallback_values[mode]
    )

    st.stop()

values = filtered["df_value"].dropna()

if mode == "Conservative":
    recommended = values.quantile(0.25)
elif mode == "Optimistic":
    recommended = values.quantile(0.75)
else:
    recommended = values.median()

st.title("🌲 DF Finder")

st.caption(
    "Prototype decision-support platform developed within the ISO 13391 framework and the Skogforsk project."
)

st.markdown("---")

st.subheader("Recommended displacement factor")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Recommended DF", round(recommended, 2))
c2.metric("Range reported in the literature",
          f"{round(values.min(),2)} – {round(values.max(),2)}")
c3.metric("Number of DF observations", len(values))
c4.metric("Number of studies", filtered["study_id"].nunique())

st.info(
    f"How close the evidence is to your case: {evidence_level}"
)

fig = px.box(
    filtered,
    y="df_value",
    points="all",
    hover_data=["wood_product"],
    title="Distribution of matching DF values"
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("Supporting evidence")

merged = filtered.merge(
    studies,
    on="study_id",
    how="left"
)

for _, row in merged.iterrows():

    st.markdown("---")

    st.markdown(
        f"### {row.get('short_ref', 'Study')} ({row.get('year', '')})"
    )

    st.markdown(
        f"**DF:** {row.get('df_value', 'NA')}"
    )

    citation = f"{row.get('authors', '')}. {row.get('title', '')}. {row.get('year', '')}."

    st.markdown(citation)

    doi = str(row.get("doi", "")).strip()

    if doi and doi.lower() != "nan":
        doi = doi.replace("https://doi.org/", "")
        st.markdown(f"[Open DOI](https://doi.org/{doi})")
