"""Compute prosecution duration and link to person outcomes.

Loads all formatted crime CSVs, extracts crime year from MesecStoritve,
and computes prosecution duration as (ClosingYear - CrimeYear).
Cross-references with the relation table to attach person/outcome details.

Outputs to `data/prosecution_duration/prosecution_analysis.csv` with columns:
- CrimeID, CrimeYear, ClosingYear, ProsecutionDuration (years)
- TotalPersons, PerpetratorsCount, VictimsCount, SentencedCount, etc.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def build_prosecution_analysis(
    formatted_dir: Path | str,
    relations_csv: Path | str,
    out_csv: Path | str,
) -> pd.DataFrame:
    """Build prosecution duration analysis with person outcome summaries.

    Args:
        formatted_dir: Directory containing formatted crime CSVs.
        relations_csv: Path to person_relations.csv.
        out_csv: Output CSV path.

    Returns:
        DataFrame with prosecution analysis.
    """
    formatted_dir = Path(formatted_dir)
    relations_csv = Path(relations_csv)
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Load relations table
    if not relations_csv.exists():
        raise FileNotFoundError(f"Relations CSV not found: {relations_csv}")

    relations_df = pd.read_csv(relations_csv, encoding="utf-8", quoting=1)
    logger.info("Loaded relations: %d rows", len(relations_df))

    files = sorted(formatted_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No formatted CSVs found in {formatted_dir}")

    rows = []
    for p in files:
        try:
            df = pd.read_csv(p, encoding="utf-8", quoting=1, low_memory=False)
        except Exception:
            df = pd.read_csv(p, encoding="cp1250", quoting=1, low_memory=False)

        # Needed columns
        needed = ["ZaporednaStevilkaKD", "MesecStoritve", "LetoZakljucnegaDokumenta"]
        for col in needed:
            if col not in df.columns:
                df[col] = None

        slice_ = df[needed].copy()

        # Extract crime year from MesecStoritve (format M.YYYY or MM.YYYY)
        def _extract_crime_year(mes):
            if pd.isna(mes):
                return None
            s = str(mes)
            try:
                year_str = s.rsplit(".", maxsplit=1)[-1]
                return int(year_str)
            except Exception:
                return None

        slice_["CrimeYear"] = slice_["MesecStoritve"].apply(_extract_crime_year)

        rows.append(slice_)

    if not rows:
        raise ValueError("No crime data found")

    df_all = pd.concat(rows, ignore_index=True, sort=False)
    df_all = df_all.dropna(subset=["ZaporednaStevilkaKD", "CrimeYear", "LetoZakljucnegaDokumenta"])

    # Rename for consistency
    df_all = df_all.rename(
        columns={
            "ZaporednaStevilkaKD": "CrimeID",
            "LetoZakljucnegaDokumenta": "ClosingYear",
        },
    )

    # Compute prosecution duration
    df_all["ProsecutionDuration"] = df_all["ClosingYear"] - df_all["CrimeYear"]

    # Group by crime and compute aggregates
    crime_groups = (
        df_all.groupby("CrimeID")
        .agg(
            {
                "CrimeYear": "first",
                "ClosingYear": "first",
                "ProsecutionDuration": "first",
            },
        )
        .reset_index()
    )

    # Join with relations to count persons by role and outcome
    relations_by_crime = (
        relations_df.groupby("CrimeID")
        .agg(
            {
                "ZaporednaStevilkaOsebeVKD": "count",  # Total persons
                "VrstaOsebe": lambda x: (x.str.contains("OSUMLJ|OSUM|OBTO", case=False, na=False)).sum(),  # perpetrators
                "IsSentenced": lambda x: x.eq(True).sum(),  # sentenced (heuristic)
                "IsOvad": lambda x: x.eq(True).sum(),  # accused persons
            },
        )
        .reset_index()
    )

    relations_by_crime = relations_by_crime.rename(
        columns={
            "ZaporednaStevilkaOsebeVKD": "TotalPersons",
            "VrstaOsebe": "PerpetratorsCount",
            "IsSentenced": "SentencedCount",
            "IsOvad": "OvadeniCount",
        },
    )

    # Count victims
    victims_by_crime = (
        relations_df[relations_df["VrstaOsebe"].str.contains("OVAD|OŠKOD|POŠKOD|ŽRTV|ŽRTEV", case=False, na=False)]
        .groupby("CrimeID")
        .size()
        .reset_index(name="VictimsCount")
    )

    # Count by outcome status
    sentenced_by_crime = (
        relations_df[relations_df["IsSentenced"] == True]
        .groupby("CrimeID")
        .size()
        .reset_index(
            name="SentencedPersons",
        )
    )
    not_sentenced_by_crime = (
        relations_df[relations_df["IsSentenced"] == False]
        .groupby("CrimeID")
        .size()
        .reset_index(
            name="NotSentencedPersons",
        )
    )
    unknown_outcome_by_crime = (
        relations_df[relations_df["IsSentenced"].isna()]
        .groupby("CrimeID")
        .size()
        .reset_index(
            name="UnknownOutcomePersons",
        )
    )

    # Count ovadeni who were not sentenced (IsOvad True and IsSentenced != True)
    ovadeni_not_sentenced_by_crime = (
        relations_df[(relations_df["IsOvad"] == True) & (relations_df["IsSentenced"] != True)]
        .groupby("CrimeID")
        .size()
        .reset_index(name="OvadeniNotSentenced")
    )

    # Merge all aggregates
    result = crime_groups.merge(relations_by_crime, on="CrimeID", how="left")
    result = result.merge(victims_by_crime, on="CrimeID", how="left")
    result = result.merge(sentenced_by_crime, on="CrimeID", how="left")
    result = result.merge(not_sentenced_by_crime, on="CrimeID", how="left")
    result = result.merge(unknown_outcome_by_crime, on="CrimeID", how="left")
    result = result.merge(ovadeni_not_sentenced_by_crime, on="CrimeID", how="left")

    # Fill NaN with 0
    numeric_cols = [
        "TotalPersons",
        "PerpetratorsCount",
        "VictimsCount",
        "SentencedCount",
        "SentencedPersons",
        "NotSentencedPersons",
        "UnknownOutcomePersons",
        "OvadeniCount",
        "OvadeniNotSentenced",
    ]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)

    result.to_csv(out_csv, index=False, quoting=1, encoding="utf-8")
    logger.info("Wrote prosecution analysis: %s (%d crime groups)", out_csv, len(result))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    formatted = Path(__file__).parents[2] / "data" / "formatted"
    relations = Path(__file__).parents[2] / "data" / "relations" / "person_relations.csv"
    out = Path(__file__).parents[2] / "data" / "prosecution_duration" / "prosecution_analysis.csv"
    build_prosecution_analysis(formatted, relations, out)
