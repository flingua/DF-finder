import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# App configuration
# ============================================================

st.set_page_config(
    page_title="DF Finder",
    page_icon="🌲",
    layout="wide",
)


# ============================================================
# Light styling
# ============================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.4rem;
        font-weight: 750;
        margin-bottom: 0.1rem;
    }
    .subtitle {
        font-size: 1.05rem;
        color: #4b5563;
        margin-bottom: 1rem;
    }
    .small-muted {
        color: #6b7280;
        font-size: 0.92rem;
    }
    .evidence-card {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.9rem;
        background-color: #ffffff;
    }
    .reference-text {
        font-size: 0.96rem;
        line-height: 1.45;
    }
    .badge {
        display: inline-block;
        padding: 0.15rem 0.45rem;
        margin-right: 0.25rem;
        margin-bottom: 0.25rem;
        border-radius: 999px;
        background-color: #eef2f7;
        color: #374151;
        font-size: 0.78rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
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

    return df_values, studies


# ============================================================
# Bibliography parsing and formatting
# ============================================================

def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "not available", "not specified", "…"}


def clean_text(value) -> str:
    if is_missing(value):
        return ""
    text = str(value).replace("\n", " ").replace("\t", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_text(text: str) -> str:
    text = clean_text(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_bibtex_fields(entry_text: str) -> dict:
    fields = {}
    # Robust enough for the ResearchRabbit BibTeX-style export used here.
    pattern = re.compile(r"(\w+)\s*=\s*\{(.*?)\}\s*,?", re.DOTALL)
    for key, value in pattern.findall(entry_text):
        fields[key.lower()] = clean_text(value)
    return fields


def parse_bibtex_file(path: Path) -> dict:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    entries = {}

    # Split at each BibTeX entry. This avoids depending on a full BibTeX parser.
    chunks = re.split(r"\n\s*@", text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith("article") and not chunk.startswith("book") and not chunk.startswith("misc"):
            continue

        header_match = re.match(r"\w+\s*\{\s*([^,]+),", chunk)
        if not header_match:
            continue

        bib_key = clean_text(header_match.group(1))
        fields = parse_bibtex_fields(chunk)
        fields["bib_key"] = bib_key
        entries[bib_key] = fields

    return entries


def split_authors(author_field: str) -> list[str]:
    if is_missing(author_field):
        return []
    return [clean_text(a) for a in re.split(r"\s+and\s+", author_field) if clean_text(a)]


def abbreviate_author(name: str) -> str:
    """Convert 'Firstname Middlename Lastname' into Vancouver-like 'Lastname FM'."""
    name = clean_text(name)
    if not name:
        return ""

    # Handle 'Last, First' if ever present.
    if "," in name:
        last, rest = [part.strip() for part in name.split(",", 1)]
        initials = "".join(part[0].upper() for part in re.split(r"[\s\-]+", rest) if part)
        return f"{last} {initials}".strip()

    parts = name.split()
    if len(parts) == 1:
        return parts[0]

    last = parts[-1]
    given = parts[:-1]
    initials = "".join(part[0].upper() for part in given if part and part[0].isalpha())
    return f"{last} {initials}".strip()


def format_authors_vancouver(author_field: str, max_authors: int = 6) -> str:
    authors = split_authors(author_field)
    if not authors:
        return "Unknown author"

    formatted = [abbreviate_author(a) for a in authors]
    formatted = [a for a in formatted if a]

    if len(formatted) > max_authors:
        return ", ".join(formatted[:max_authors]) + ", et al"
    return ", ".join(formatted)


def format_vancouver_from_bib(entry: dict) -> str:
    authors = format_authors_vancouver(entry.get("author", ""))
    title = clean_text(entry.get("title", ""))
    journal = clean_text(entry.get("journal", ""))
    year = clean_text(entry.get("year", ""))

    parts = []
    if authors:
        parts.append(authors + ".")
    if title:
        parts.append(title.rstrip(".") + ".")
    if journal:
        parts.append(journal.rstrip(".") + ".")
    if year:
        parts.append(year.rstrip(".") + ".")

    return " ".join(parts).strip()


def format_vancouver_from_study(row: pd.Series) -> str:
    authors = clean_text(row.get("authors", ""))
    title = clean_text(row.get("title", ""))
    journal = clean_text(row.get("journal_or_source", row.get("journal", "")))
    year = clean_text(row.get("year", ""))

    # The cleaned Excel often already has 'Bergman et al.'; keep it if full authors are unavailable.
    if not authors:
        authors = "Unknown author"

    parts = []
    parts.append(authors.rstrip(".") + ".")
    if title:
        parts.append(title.rstrip(".") + ".")
    if journal:
        parts.append(journal.rstrip(".") + ".")
    if year:
        parts.append(str(year).rstrip(".") + ".")
    return " ".join(parts).strip()


def first_author_last_from_bib(entry: dict) -> str:
    authors = split_authors(entry.get("author", ""))
    if not authors:
        return ""
    first = authors[0]
    if "," in first:
        last = first.split(",", 1)[0]
    else:
        last = first.split()[-1]
    return normalize_text(last)


def build_bib_indices(entries: dict) -> dict:
    by_doi = {}
    by_author_year = {}
    by_title = {}

    for key, entry in entries.items():
        doi = normalize_text(entry.get("doi", ""))
        if doi:
            by_doi[doi] = key

        year = clean_text(entry.get("year", ""))
        last = first_author_last_from_bib(entry)
        if last and year:
            by_author_year.setdefault((last, str(year)), []).append(key)

        title = normalize_text(entry.get("title", ""))
        if title:
            by_title[key] = title

    return {"by_doi": by_doi, "by_author_year": by_author_year, "by_title": by_title}


def find_bib_entry_for_study(study_row: pd.Series, entries: dict, indices: dict) -> dict | None:
    if not entries:
        return None

    doi = normalize_text(study_row.get("doi", ""))
    if doi and doi in indices["by_doi"]:
        return entries[indices["by_doi"][doi]]

    title = normalize_text(study_row.get("title", ""))
    if title:
        best_key = None
        best_score = 0
        for key, bib_title in indices["by_title"].items():
            score = SequenceMatcher(None, title, bib_title).ratio()
            if score > best_score:
                best_key = key
                best_score = score
        if best_key and best_score >= 0.72:
            return entries[best_key]

    short_ref = normalize_text(study_row.get("short_ref", ""))
    year = clean_text(study_row.get("year", ""))
    if short_ref and year:
        # Short refs can include descriptors. The first word is usually the first author.
        first_token = short_ref.split()[0]
        candidates = indices["by_author_year"].get((first_token, str(year)), [])
        if len(candidates) == 1:
            return entries[candidates[0]]

    return None


@st.cache_data
def load_bibliography():
    bib_path = Path("data") / "biblio.txt"
    entries = parse_bibtex_file(bib_path)
    indices = build_bib_indices(entries)
    return entries, indices


# ============================================================
# Helper functions
# ============================================================

def unique_options(df, column):
    if column not in df.columns:
        return []
    return sorted(df[column].dropna().astype(str).unique())


# ============================================================
# Södra-facing prototype ontology
# ============================================================

ASSORTMENT_ORDER = [
    "All products",
    "Sawn wood products",
    "Engineered wood / building systems",
    "Paper pulp",
    "Dissolving pulp / textiles",
    "Bioenergy & fuels",
    "Other bioproducts",
    "Other / unclassified",
]


def build_search_text(row: pd.Series) -> str:
    cols = [
        "product_group",
        "wood_product",
        "end_use",
        "alternative_product",
        "notes",
    ]

    values = []
    for col in cols:
        if col in row.index and not is_missing(row.get(col)):
            values.append(str(row.get(col)))

    return " ".join(values).lower()


def classify_assortment(row: pd.Series) -> str:
    text = build_search_text(row)

    if any(k in text for k in [
        "dissolving", "viscose", "lyocell", "textile", "rayon",
        "cellulosic fibre", "cellulosic fiber",
    ]):
        return "Dissolving pulp / textiles"

    if any(k in text for k in [
        "bioenergy", "energy", "heat", "electricity", "pellet", "fuelwood",
        "biofuel", "biomethanol", "methanol", "chp", "oil", "coal",
        "natural gas",
    ]):
        return "Bioenergy & fuels"

    if any(k in text for k in [
        "clt", "cross-laminated", "cross laminated", "glulam", "i-joist",
        "engineered wood", "wood frame", "timber frame", "building structure",
        "structural frame", "house", "building",
    ]):
        return "Engineered wood / building systems"

    if any(k in text for k in [
        "paper", "pulp", "carton", "cardboard", "packaging", "fibre product",
        "fiber product", "tissue",
    ]):
        return "Paper pulp"

    if any(k in text for k in [
        "sawn", "lumber", "solid wood", "timber", "decking", "siding",
        "cladding", "flooring", "door", "window", "railroad ties",
        "railway sleeper", "utility pole",
    ]):
        return "Sawn wood products"

    if any(k in text for k in [
        "biochemical", "chemical", "lignin", "biochar", "biomaterial",
        "bioplastic", "plastic composite",
    ]):
        return "Other bioproducts"

    return "Other / unclassified"


def classify_end_use(row: pd.Series) -> str:
    text = build_search_text(row)

    if any(k in text for k in [
        "clt", "glulam", "frame", "structure", "structural", "house", "building",
    ]):
        return "Structural / building systems"

    if any(k in text for k in ["floor", "flooring"]):
        return "Flooring"

    if "decking" in text:
        return "Decking"

    if any(k in text for k in ["siding", "cladding", "exterior panel"]):
        return "Cladding / exterior"

    if any(k in text for k in ["door", "window", "joinery", "furniture"]):
        return "Joinery / furniture"

    if any(k in text for k in ["packaging", "pallet", "carton", "cardboard", "box"]):
        return "Packaging"

    if "tissue" in text:
        return "Tissue"

    if any(k in text for k in [
        "printing", "graphic paper", "specialty paper", "speciality paper",
    ]):
        return "Paper / specialty paper"

    if "viscose" in text:
        return "Viscose"

    if "lyocell" in text:
        return "Lyocell"

    if any(k in text for k in ["textile", "rayon"]):
        return "Other textile fibre"

    if any(k in text for k in ["heat", "district heating"]):
        return "Heat"

    if any(k in text for k in ["electricity", "power", "chp"]):
        return "Electricity / CHP"

    if any(k in text for k in ["fuel", "pellet", "methanol", "bioenergy"]):
        return "Fuel"

    original = clean_text(row.get("end_use", ""))
    if original:
        return original

    return "General / unspecified"


def add_interface_ontology(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["assortment"] = out.apply(classify_assortment, axis=1)
    out["use_case"] = out.apply(classify_end_use, axis=1)
    return out


def cascading_options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return ["All"]

    values = sorted(
        v for v in df[column].dropna().astype(str).unique()
        if clean_text(v)
    )
    return ["All"] + values


def apply_smart_filters(
    df: pd.DataFrame,
    assortment: str,
    use_case: str,
    alternative_product: str,
    geography: str,
) -> pd.DataFrame:
    filtered = df.copy()

    if assortment != "All products":
        filtered = filtered[filtered["assortment"] == assortment]

    if use_case != "All":
        filtered = filtered[filtered["use_case"] == use_case]

    if alternative_product != "All" and "alternative_product" in filtered.columns:
        filtered = filtered[
            filtered["alternative_product"].astype(str) == alternative_product
        ]

    if geography != "All" and "geography" in filtered.columns:
        filtered = filtered[
            filtered["geography"].astype(str) == geography
        ]

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
        "n_values": int(len(values)),
        "n_studies": int(filtered["study_id"].nunique()),
    }


def confidence_label(n_values, n_studies):
    if n_values >= 10 and n_studies >= 5:
        return "High"
    if n_values >= 4 and n_studies >= 2:
        return "Medium"
    if n_values >= 1:
        return "Low"
    return "No data"


def make_doi_link(doi: str) -> str:
    doi = clean_text(doi)
    if not doi:
        return ""
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return f"https://doi.org/{doi}"


def attach_reference_numbers(filtered_full: pd.DataFrame) -> pd.DataFrame:
    out = filtered_full.copy()
    study_order = (
        out[["study_id", "short_ref", "year"]]
        .drop_duplicates()
        .sort_values(["short_ref", "year", "study_id"], na_position="last")
    )
    ref_map = {sid: i + 1 for i, sid in enumerate(study_order["study_id"].tolist())}
    out["ref_no"] = out["study_id"].map(ref_map)
    out["citation_label"] = out["ref_no"].apply(lambda x: f"[{int(x)}]" if pd.notna(x) else "")
    return out


def render_supporting_evidence(filtered_full: pd.DataFrame, bib_entries: dict, bib_indices: dict):
    st.subheader("Supporting evidence")
    st.caption(
        "Each card groups the DF observations by source publication. References are formatted in Vancouver style where metadata are available."
    )

    if filtered_full.empty:
        st.warning("No supporting evidence available for this filter combination.")
        return

    study_ids = (
        filtered_full[["study_id", "ref_no", "short_ref", "year"]]
        .drop_duplicates()
        .sort_values("ref_no")
    )

    for _, study_stub in study_ids.iterrows():
        study_id = study_stub["study_id"]
        ref_no = int(study_stub["ref_no"])
        group = filtered_full[filtered_full["study_id"] == study_id].copy()
        study_row = group.iloc[0]

        bib_entry = find_bib_entry_for_study(study_row, bib_entries, bib_indices)
        if bib_entry:
            citation = format_vancouver_from_bib(bib_entry)
            doi = clean_text(bib_entry.get("doi", ""))
        else:
            citation = format_vancouver_from_study(study_row)
            doi = clean_text(study_row.get("doi", ""))

        short_ref = clean_text(study_row.get("short_ref", "")) or f"Study {study_id}"
        year = clean_text(study_row.get("year", ""))
        heading = f"[{ref_no}] {short_ref}"
        if year:
            heading += f" ({year})"

        with st.expander(heading, expanded=ref_no <= 3):
            st.markdown(f"<div class='reference-text'>{citation}</div>", unsafe_allow_html=True)

            doi_link = make_doi_link(doi)
            if doi_link:
                st.markdown(f"[Open DOI]({doi_link})")

            st.markdown("**DF observations from this source**")
            obs_cols = []
            for col in ["wood_product", "alternative_product", "end_use", "geography", "df_value"]:
                if col in group.columns:
                    obs_cols.append(col)

            obs = group[obs_cols].copy()
            rename_map = {
                "wood_product": "Wood product / product system",
                "alternative_product": "Alternative product",
                "end_use": "End use",
                "geography": "Geography",
                "df_value": "DF",
            }
            obs = obs.rename(columns=rename_map)

            # Hide useless empty columns.
            keep_cols = []
            for col in obs.columns:
                series = obs[col]
                if not series.apply(is_missing).all():
                    keep_cols.append(col)
            obs = obs[keep_cols]

            st.table(obs.reset_index(drop=True))

            notes = [clean_text(n) for n in group.get("notes", pd.Series(dtype=str)).dropna().unique()]
            notes = [n for n in notes if n]
            if notes:
                with st.expander("Methodological notes"):
                    for note in notes:
                        st.markdown(f"- {note}")


# ============================================================
# Load data
# ============================================================

df_values, studies = load_data()
df_values = add_interface_ontology(df_values)
bib_entries, bib_indices = load_bibliography()


# ============================================================
# Header
# ============================================================

logo_path = Path("assets") / "skogforsk_logo.png"
header_left, header_right = st.columns([0.78, 0.22])

with header_left:
    st.markdown("<div class='main-title'>🌲 DF Finder</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='subtitle'>Evidence-based exploration of displacement factors for wood-based products</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "Prototype decision-support platform developed in the context of the ISO 13391 framework and the Skogforsk project <i>Standard för skogens klimateffekt</i>.",
        unsafe_allow_html=True,
    )

with header_right:
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)
    else:
        st.markdown("**Skogforsk**")
        st.caption("Logo placeholder")

st.markdown("---")

with st.expander("About this prototype", expanded=False):
    st.markdown(
        """
        Displacement factors (DFs) are used to estimate the potential climate benefit associated with wood-based products substituting more greenhouse gas intensive products or energy systems.

        Published DF values vary substantially because studies differ in product systems, counterfactual products, geographic scope, system boundaries, and assumptions about end-use and market realization.

        This prototype is not intended to provide a single universally correct DF. It is an evidence navigation tool: it helps users explore published values, understand their spread, and identify transparent literature-based estimates for a selected product context.
        """
    )

with st.expander("Important limitations", expanded=False):
    st.markdown(
        """
        - Values shown here represent displacement potentials reported or derived from the literature. They should not automatically be interpreted as realized or guaranteed emission reductions.
        - Recommendation values are statistical summaries of the filtered evidence subset and do not replace expert assessment.
        - Some product categories remain heterogeneous in this prototype version and the ontology is still under active development.
        - The app is intended for research, exploration, and dialogue. It is not an official reporting standard.
        """
    )


# ============================================================
# Sidebar filters
# ============================================================

st.sidebar.header("Find evidence for your product")
st.sidebar.caption(
    "Choose the product assortment first. The following choices narrow automatically."
)

assortment_values = [
    a for a in ASSORTMENT_ORDER
    if a == "All products" or a in set(df_values["assortment"].dropna())
]

assortment = st.sidebar.selectbox(
    "What product assortment are you working with?",
    assortment_values,
)

df_after_assortment = df_values.copy()
if assortment != "All products":
    df_after_assortment = df_after_assortment[
        df_after_assortment["assortment"] == assortment
    ]

use_case = st.sidebar.selectbox(
    "What is the product mainly used for?",
    cascading_options(df_after_assortment, "use_case"),
)

df_after_use = df_after_assortment.copy()
if use_case != "All":
    df_after_use = df_after_use[df_after_use["use_case"] == use_case]

alternative_product = st.sidebar.selectbox(
    "What does it replace in the study?",
    cascading_options(df_after_use, "alternative_product"),
)

df_after_alt = df_after_use.copy()
if alternative_product != "All" and "alternative_product" in df_after_alt.columns:
    df_after_alt = df_after_alt[
        df_after_alt["alternative_product"].astype(str) == alternative_product
    ]

geography = st.sidebar.selectbox(
    "Where is the evidence from?",
    cascading_options(df_after_alt, "geography"),
)

mode = st.sidebar.radio(
    "Which summary do you want to see?",
    ["Conservative", "Central", "Optimistic"],
    index=1,
    help=(
        "Conservative = 25th percentile; Central = median; "
        "Optimistic = 75th percentile of matching DF observations."
    ),
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Current version:** prototype v0.5")
st.sidebar.caption(
    "Product assortment categories are a prototype interface ontology and will be refined with stakeholders."
)


# ============================================================
# Filter data
# ============================================================

filtered = apply_smart_filters(
    df=df_values,
    assortment=assortment,
    use_case=use_case,
    alternative_product=alternative_product,
    geography=geography,
)

filtered = filtered.dropna(subset=["df_value"])
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
    recommendation["n_studies"],
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Recommended DF", recommendation["recommended"])
col2.metric("Observed range", f"{recommendation['min']} – {recommendation['max']}")
col3.metric("DF observations", recommendation["n_values"])
col4.metric("Evidence density", confidence)

st.info(
    "The recommended value is a statistical summary of the currently filtered literature subset. It should be interpreted as an indicative displacement potential, not as a guaranteed realized climate effect."
)


# ============================================================
# Merge with study metadata and assign reference numbers
# ============================================================

filtered_full = filtered.merge(
    studies,
    on="study_id",
    how="left",
    suffixes=("", "_study"),
)

# Fill common fields from either source when merge creates duplicates.
for col in ["short_ref", "year"]:
    study_col = f"{col}_study"
    if study_col in filtered_full.columns:
        filtered_full[col] = filtered_full[col].combine_first(filtered_full[study_col])

filtered_full = attach_reference_numbers(filtered_full)


# ============================================================
# Evidence-over-time plot
# ============================================================

st.subheader("DF evidence over time")
st.caption(
    "Each point is one DF observation. Use the filters in the sidebar to explore how the evidence changes by product assortment, use, alternative product, and geography."
)

plot_df = filtered_full.copy()

plot_df["publication_year"] = pd.to_numeric(
    plot_df["year"],
    errors="coerce",
)

plot_df = plot_df.dropna(
    subset=["publication_year", "df_value"]
).copy()

plot_df["publication_year"] = plot_df["publication_year"].astype(int)

plot_df["Reference"] = (
    plot_df["citation_label"].fillna("")
    + " "
    + plot_df["short_ref"].fillna("")
).str.strip()

hover_fields = {
    "df_value": ":.2f",
    "publication_year": True,
    "Reference": True,
}

for col in [
    "assortment",
    "use_case",
    "wood_product",
    "alternative_product",
    "geography",
]:
    if col in plot_df.columns:
        hover_fields[col] = True

fig = px.scatter(
    plot_df,
    x="publication_year",
    y="df_value",
    hover_name="wood_product" if "wood_product" in plot_df.columns else None,
    hover_data=hover_fields,
    labels={
        "publication_year": "Publication year",
        "df_value": "Displacement factor (tCO₂e / tCO₂e biogenic carbon)",
        "assortment": "Product assortment",
        "use_case": "Use",
        "alternative_product": "Alternative product",
        "geography": "Geography",
    },
    title="DF observations by publication year",
)

fig.update_traces(
    marker={
        "size": 10,
        "opacity": 0.78,
        "line": {"width": 0.5},
    }
)

if not plot_df.empty:
    min_year = int(plot_df["publication_year"].min())
    max_year = int(plot_df["publication_year"].max())

    fig.update_xaxes(
        range=[min_year - 1, max_year + 1],
        dtick=5 if max_year - min_year >= 10 else 1,
    )

fig.update_layout(
    yaxis_title="Displacement factor (tCO₂e / tCO₂e biogenic carbon)",
    xaxis_title="Publication year",
    showlegend=False,
)

st.plotly_chart(fig, use_container_width=True)

if not plot_df.empty:
    years = plot_df["publication_year"]
    summary1, summary2, summary3, summary4 = st.columns(4)

    summary1.metric(
        "Evidence period",
        f"{int(years.min())}–{int(years.max())}",
    )

    summary2.metric(
        "Median DF",
        f"{plot_df['df_value'].median():.2f}",
    )

    summary3.metric(
        "Latest study year",
        int(years.max()),
    )

    summary4.metric(
        "Studies shown",
        int(plot_df["study_id"].nunique()),
    )


# ============================================================
# Supporting evidence and bibliography
# ============================================================

render_supporting_evidence(filtered_full, bib_entries, bib_indices)


# ============================================================
# Methodological footer
# ============================================================

st.markdown("---")
with st.expander("How recommendation values are calculated"):
    st.markdown(
        """
        The app first filters the displacement factor database according to the selected product assortment, use, alternative product, and geography. It then summarizes the remaining DF observations using a transparent percentile-based rule:

        - **Conservative:** 25th percentile of matching observations
        - **Central:** median of matching observations
        - **Optimistic:** 75th percentile of matching observations

        The observed range is shown separately to make the spread of the literature visible. Future versions may include weighting by evidence quality, geography, system boundary, and relevance to Swedish conditions.
        """
    )
