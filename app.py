import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
from html import escape


# ============================================================
# App configuration
# ============================================================

st.set_page_config(
    page_title="DF Finder",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# Styling
# ============================================================

st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1350px;
    }
    .hero-box {
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        background: linear-gradient(135deg, #f4f8f4 0%, #eef5ef 100%);
        border: 1px solid #d8e5d8;
        margin-bottom: 1.2rem;
    }
    .small-caps {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
        color: #5d6b5d;
        font-weight: 700;
    }
    .hero-title {
        font-size: 2.35rem;
        line-height: 1.1;
        font-weight: 800;
        margin: 0.2rem 0 0.4rem 0;
        color: #173b22;
    }
    .hero-subtitle {
        font-size: 1.03rem;
        color: #334233;
        max-width: 950px;
    }
    .section-card {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        border: 1px solid #e2e8e2;
        background-color: #ffffff;
        margin-bottom: 0.8rem;
    }
    .evidence-card {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        border: 1px solid #dde6dd;
        background-color: #fbfdfb;
        margin-bottom: 0.85rem;
    }
    .evidence-title {
        font-size: 1.02rem;
        font-weight: 750;
        color: #173b22;
        margin-bottom: 0.2rem;
    }
    .muted {
        color: #637063;
        font-size: 0.92rem;
    }
    .badge {
        display: inline-block;
        padding: 0.18rem 0.48rem;
        margin-right: 0.25rem;
        margin-top: 0.15rem;
        border-radius: 999px;
        background-color: #edf4ed;
        color: #234b2a;
        font-size: 0.78rem;
        border: 1px solid #d6e4d6;
    }
    .doi-button a {
        text-decoration: none;
        font-weight: 650;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# Data loading
# ============================================================

@st.cache_data
def load_data():
    data_dir = Path("data")
    excel_path = data_dir / "df_master_extraction_cleaned.xlsx"

    df_values = pd.read_excel(excel_path, sheet_name="df_values")
    studies = pd.read_excel(excel_path, sheet_name="studies")

    df_values["df_value"] = pd.to_numeric(df_values["df_value"], errors="coerce")

    # Make sure expected text columns exist even if the workbook changes later.
    for col in [
        "df_id", "study_id", "product_group", "wood_product", "alternative_product",
        "end_use", "geography", "notes", "evidence_quality", "sweden_relevance"
    ]:
        if col not in df_values.columns:
            df_values[col] = pd.NA

    for col in [
        "study_id", "authors", "year", "title", "journal", "doi", "country_region", "notes"
    ]:
        if col not in studies.columns:
            studies[col] = pd.NA

    return df_values, studies


df_values, studies = load_data()


# ============================================================
# Helper functions
# ============================================================

def clean_text(value, fallback="Not specified"):
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "not available"}:
        return fallback
    return text


def unique_options(df, column):
    if column not in df.columns:
        return []
    return sorted(df[column].dropna().astype(str).unique())


def apply_filters(df, product_group, end_use, geography):
    filtered = df.copy()

    if product_group != "All":
        filtered = filtered[filtered["product_group"].astype(str) == product_group]

    if end_use != "All":
        filtered = filtered[filtered["end_use"].astype(str) == end_use]

    if geography != "All":
        filtered = filtered[filtered["geography"].astype(str) == geography]

    return filtered


def calculate_recommendation(filtered, mode):
    values = filtered["df_value"].dropna()

    if values.empty:
        return None

    if mode == "Conservative":
        recommended = values.quantile(0.25)
        method = "25th percentile of matching DF observations"
    elif mode == "Optimistic":
        recommended = values.quantile(0.75)
        method = "75th percentile of matching DF observations"
    else:
        recommended = values.median()
        method = "median of matching DF observations"

    return {
        "recommended": round(float(recommended), 2),
        "min": round(float(values.min()), 2),
        "max": round(float(values.max()), 2),
        "median": round(float(values.median()), 2),
        "q25": round(float(values.quantile(0.25)), 2),
        "q75": round(float(values.quantile(0.75)), 2),
        "n_values": int(len(values)),
        "n_studies": int(filtered["study_id"].nunique()),
        "method": method
    }


def confidence_label(n_values, n_studies):
    if n_values >= 10 and n_studies >= 5:
        return "High"
    if n_values >= 4 and n_studies >= 2:
        return "Medium"
    if n_values >= 1:
        return "Low"
    return "No data"


def doi_url(doi):
    doi = clean_text(doi, fallback="")
    if not doi:
        return None
    doi = doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "").strip()
    if doi.lower() in {"not available", "na", "n/a"}:
        return None
    return f"https://doi.org/{doi}"


def format_vancouver_reference(row, number=None):
    authors = clean_text(row.get("authors"), fallback="Unknown author")
    title = clean_text(row.get("title"), fallback="Untitled study")
    journal = clean_text(row.get("journal"), fallback="")
    year = clean_text(row.get("year"), fallback="n.d.")
    doi = clean_text(row.get("doi"), fallback="")

    # Vancouver-inspired compact style. Exact author initials depend on available metadata.
    prefix = f"{number}. " if number is not None else ""
    pieces = [f"{prefix}{authors}. {title}."]
    if journal:
        pieces.append(f" {journal}.")
    if year:
        pieces.append(f" {year}.")
    if doi:
        pieces.append(f" doi:{doi}")
    return "".join(pieces)


def build_supporting_data(filtered, studies):
    merged = filtered.merge(
        studies,
        on="study_id",
        how="left",
        suffixes=("", "_study")
    )

    study_order = (
        merged[["study_id", "authors", "year", "title", "journal", "doi", "country_region", "notes_study"]]
        .drop_duplicates(subset=["study_id"])
        .sort_values(["year", "authors"], na_position="last")
        .reset_index(drop=True)
    )
    study_order["bib_number"] = range(1, len(study_order) + 1)

    merged = merged.merge(
        study_order[["study_id", "bib_number"]],
        on="study_id",
        how="left"
    )

    return merged, study_order


# ============================================================
# Sidebar
# ============================================================

assets_dir = Path("assets")
logo_path = assets_dir / "skogforsk_logo.png"

if logo_path.exists():
    st.sidebar.image(str(logo_path), use_container_width=True)
else:
    st.sidebar.markdown("### 🌲 DF Finder")

st.sidebar.caption("Prototype v0.2 · ISO 13391 / AP4")
st.sidebar.markdown("---")
st.sidebar.header("Product context")

product_group = st.sidebar.selectbox(
    "Product group",
    ["All"] + unique_options(df_values, "product_group"),
    help="Broad wood-product family used to filter the DF database."
)

end_use = st.sidebar.selectbox(
    "End use",
    ["All"] + unique_options(df_values, "end_use"),
    help="Application or market context in which the wood product is used."
)

geography = st.sidebar.selectbox(
    "Geography",
    ["All"] + unique_options(df_values, "geography"),
    help="Geographic scope reported or inferred for the DF observation."
)

mode = st.sidebar.radio(
    "Recommendation style",
    ["Conservative", "Central", "Optimistic"],
    index=1,
    help=(
        "Conservative uses the lower quartile, Central uses the median, "
        "and Optimistic uses the upper quartile of the filtered evidence."
    )
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "This prototype is intended for exploration and methodological discussion. "
    "It is not an official reporting tool."
)


# ============================================================
# Header / hero
# ============================================================

st.markdown(
    """
    <div class="hero-box">
        <div class="small-caps">Standard för skogens klimateffekt · ISO 13391 implementation support</div>
        <div class="hero-title">🌲 DF Finder</div>
        <div class="hero-subtitle">
            Interactive prototype for exploring published displacement factors for wood-based products.
            The tool helps users identify evidence-based DF ranges by product category, end use, geography,
            and recommendation philosophy.
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

with st.expander("About this prototype", expanded=False):
    st.markdown(
        """
        Displacement factors (DFs) are used to estimate the potential climate benefit obtained when
        wood-based products substitute more greenhouse-gas-intensive materials or energy systems.

        Published DF values vary substantially because studies differ in product systems, geographic
        context, substituted alternatives, system boundaries, end-use assumptions, and treatment of
        value-chain emissions.

        This tool is therefore not designed to provide one universally correct DF. It acts as an
        **evidence navigation and interpretation system**: users select a context, and the app summarizes
        the matching literature values in a transparent way.
        """
    )

with st.expander("How to use the tool", expanded=False):
    st.markdown(
        """
        1. Select a product group, end use, and geography in the sidebar.
        2. Choose a recommendation style: conservative, central, or optimistic.
        3. Inspect the recommended value, uncertainty range, and supporting evidence.
        4. Use the bibliography cards to trace each DF observation back to its source.
        """
    )

with st.expander("Limitations and interpretation notes", expanded=False):
    st.markdown(
        """
        - Values represent **displacement potentials** reported or derived from the literature, not guaranteed realized emission reductions.
        - Different studies use different system boundaries; some include value-chain emissions, end-use effects, storage effects, or broader system effects.
        - The current ontology is under development and some categories still contain heterogeneous applications.
        - The recommendation is a transparent statistical summary of the filtered evidence and does not replace expert judgement.
        - This prototype is intended for research, discussion, and development; it is not an official reporting standard.
        """
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
    st.warning("No matching DF values found for the selected filters. Try broadening the product, end-use, or geography selection.")
    st.stop()

confidence = confidence_label(
    recommendation["n_values"],
    recommendation["n_studies"]
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Recommended DF", recommendation["recommended"])
col2.metric("Observed range", f"{recommendation['min']} – {recommendation['max']}")
col3.metric("DF observations", recommendation["n_values"])
col4.metric("Evidence confidence", confidence)

st.caption(
    f"Recommendation method: {recommendation['method']}. "
    f"The central median of the selected evidence is {recommendation['median']}."
)

st.info(
    "Interpretation: the recommended value is an indicative displacement potential derived from the filtered literature subset. "
    "It should not be interpreted as guaranteed realized substitution."
)


# ============================================================
# Supporting data / bibliography numbering
# ============================================================

filtered_full, supporting_studies = build_supporting_data(filtered, studies)
filtered_full = filtered_full.dropna(subset=["df_value"]).copy()
filtered_full["Reference"] = filtered_full["bib_number"].apply(lambda x: f"[{int(x)}]" if pd.notna(x) else "")


# ============================================================
# Plot
# ============================================================

st.subheader("Distribution of matching DF values")

fig = px.box(
    filtered_full,
    y="df_value",
    points="all",
    hover_name="wood_product",
    hover_data={
        "Reference": True,
        "study_id": True,
        "product_group": True,
        "end_use": True,
        "geography": True,
        "df_value": ":.2f",
        "notes": False,
        "bib_number": False,
    },
    title="DF value distribution for selected evidence"
)

fig.update_layout(
    yaxis_title="Displacement factor (tCO₂e / tCO₂e biogenic carbon)",
    xaxis_title="",
    showlegend=False,
    margin=dict(l=20, r=20, t=55, b=20)
)

st.plotly_chart(fig, use_container_width=True)

st.caption("Hover over points to identify the product, DF value, and numbered source in the bibliography below.")


# ============================================================
# Evidence cards
# ============================================================

st.subheader("Supporting DF observations")

for _, row in filtered_full.sort_values(["bib_number", "df_value", "wood_product"]).iterrows():
    bib_no = int(row["bib_number"]) if pd.notna(row.get("bib_number")) else "?"
    product = clean_text(row.get("wood_product"))
    alternative = clean_text(row.get("alternative_product"))
    end_use_value = clean_text(row.get("end_use"))
    geo = clean_text(row.get("geography"))
    df_val = row.get("df_value")
    notes = clean_text(row.get("notes"), fallback="")

    doi = row.get("doi")
    link = doi_url(doi)

    st.markdown(
        f"""
        <div class="evidence-card">
            <div class="evidence-title">[{bib_no}] {escape(product)} — DF = {df_val:.2f}</div>
            <div class="muted">
                <span class="badge">{escape(end_use_value)}</span>
                <span class="badge">{escape(geo)}</span>
                <span class="badge">Alternative: {escape(alternative)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if notes:
        with st.expander(f"Methodological note for [{bib_no}] {product}"):
            st.write(notes)


# ============================================================
# Bibliography
# ============================================================

st.subheader("Bibliography of supporting studies")

for _, study in supporting_studies.sort_values("bib_number").iterrows():
    bib_no = int(study["bib_number"])
    reference = format_vancouver_reference(study, number=bib_no)
    link = doi_url(study.get("doi"))
    study_notes = clean_text(study.get("notes_study"), fallback="")

    st.markdown(f"**{reference}**")
    if link:
        st.markdown(f"[Open DOI]({link})")
    if study_notes:
        with st.expander(f"Study notes [{bib_no}]"):
            st.write(study_notes)
    st.markdown("---")


# ============================================================
# Optional advanced view
# ============================================================

with st.expander("Advanced: show compact extraction table", expanded=False):
    compact_cols = [
        "df_id", "study_id", "bib_number", "product_group", "wood_product",
        "alternative_product", "end_use", "geography", "df_value", "notes"
    ]
    compact_cols = [c for c in compact_cols if c in filtered_full.columns]
    st.dataframe(
        filtered_full[compact_cols].sort_values(["bib_number", "df_value"]),
        use_container_width=True,
        hide_index=True
    )
