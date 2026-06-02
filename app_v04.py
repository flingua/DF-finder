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

st.sidebar.header("Select product context")
st.sidebar.caption("Start broad, then narrow the search if needed.")

product_group = st.sidebar.selectbox(
    "Product group",
    ["All"] + unique_options(df_values, "product_group"),
)

end_use = st.sidebar.selectbox(
    "End use",
    ["All"] + unique_options(df_values, "end_use"),
)

geography = st.sidebar.selectbox(
    "Geography",
    ["All"] + unique_options(df_values, "geography"),
)

mode = st.sidebar.radio(
    "Recommendation style",
    ["Conservative", "Central", "Optimistic"],
    index=1,
    help="Conservative = 25th percentile; Central = median; Optimistic = 75th percentile of matching DF observations.",
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Current version:** prototype v0.3")
st.sidebar.caption("Database and ontology under active development.")


# ============================================================
# Filter data
# ============================================================

filtered = apply_filters(df_values, product_group, end_use, geography)
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
# Plot
# ============================================================

st.subheader("Distribution of matching DF values")

plot_df = filtered_full.copy()
plot_df["Reference"] = plot_df["citation_label"].fillna("") + " " + plot_df["short_ref"].fillna("")

fig = px.box(
    plot_df,
    y="df_value",
    points="all",
    hover_name="wood_product",
    hover_data={
        "Reference": True,
        "df_value": True,
        "end_use": True,
        "geography": True,
        "product_group": True,
        "wood_product": False,
    },
    title="DF value distribution for the selected evidence subset",
)

fig.update_layout(
    yaxis_title="Displacement factor (tCO₂e / tCO₂e biogenic carbon)",
    xaxis_title="",
    showlegend=False,
)

st.plotly_chart(fig, use_container_width=True)


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
        The app first filters the displacement factor database according to the selected product group, end use, and geography. It then summarizes the remaining DF observations using a transparent percentile-based rule:

        - **Conservative:** 25th percentile of matching observations
        - **Central:** median of matching observations
        - **Optimistic:** 75th percentile of matching observations

        The observed range is shown separately to make the spread of the literature visible. Future versions may include weighting by evidence quality, geography, system boundary, and relevance to Swedish conditions.
        """
    )
