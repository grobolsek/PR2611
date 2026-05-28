"""Build a person–crime relation table from formatted crime CSVs.

Produces a CSV with one row per person reference containing:
- `ZaporednaStevilkaOsebeVKD` (encoded id: crime_id * 1000 + person_seq)
- `CrimeID` (ZaporednaStevilkaKD)
- `VrstaOsebe` (original role text: victim, perpetrator, etc.)
- `VrstaZakljucnegaDokumenta`, `LetoZakljucnegaDokumenta` (outcome fields)
- `IsSentenced` (heuristic boolean inferred from outcome text — may be empty)
- `IsOvad` (boolean: whether the person is listed as ovaden / accused)

This module is intentionally conservative: it preserves original text
fields and supplies small, well-documented heuristics. `IsOvad` is derived
from the `VrstaOsebe` text (contains "OVAD"). The output is written to
`data/relations/person_relations.csv`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _is_sentenced(vrsta_zak_doc: object) -> bool | None:
    if pd.isna(vrsta_zak_doc):
        return None
    s = str(vrsta_zak_doc).upper()
    # Heuristic: presence of words typically associated with conviction
    if any(k in s for k in ("OBSOD", "SOD", "SODBA", "KAZEN", "KAZNOV")):
        return True
    # Keywords for dismissal/abandonment
    if any(k in s for k in ("ZAPUST", "ODBIJA", "ZAVRN", "ZAPUSTI", "NI ZAKLJ")):
        return False
    return None


def build_relations(formatted_dir: Path | str, out_csv: Path | str) -> pd.DataFrame:
    formatted_dir = Path(formatted_dir)
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(formatted_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No formatted CSVs found in {formatted_dir}")

    rows = []
    for p in files:
        try:
            df = pd.read_csv(p, encoding="utf-8", quoting=1, low_memory=False)
        except Exception:
            df = pd.read_csv(p, encoding="cp1250", quoting=1, low_memory=False)

        # Keep only columns we care about (add missing ones as NA)
        needed = [
            "ZaporednaStevilkaOsebeVKD",
            "ZaporednaStevilkaKD",
            "VrstaOsebe",
            "VrstaZakljucnegaDokumenta",
            "LetoZakljucnegaDokumenta",
        ]
        for col in needed:
            if col not in df.columns:
                df[col] = None

        # Rows that mention a person (either encoded id or a non-null VrstaOsebe)
        mask = df["ZaporednaStevilkaOsebeVKD"].notna() | df["VrstaOsebe"].notna()
        slice_ = df.loc[mask, needed].copy().reset_index(drop=True)

        rows.append(slice_)

    if not rows:
        df_out = pd.DataFrame(
            columns=[
                "ZaporednaStevilkaOsebeVKD",
                "CrimeID",
                "VrstaOsebe",
                "VrstaZakljucnegaDokumenta",
                "LetoZakljucnegaDokumenta",
                "IsSentenced",
            ],
        )
        df_out.to_csv(out_csv, index=False, quoting=1, encoding="utf-8")
        return df_out

    df_all = pd.concat(rows, ignore_index=True, sort=False)

    # Extract CrimeID: decode from ZaporednaStevilkaOsebeVKD (crime_id * 1000 + seq)
    # or use ZaporednaStevilkaKD as fallback
    def _get_crime_id(row):
        if pd.notna(row["ZaporednaStevilkaOsebeVKD"]):
            try:
                v = int(float(row["ZaporednaStevilkaOsebeVKD"]))
                crime_id = v // 1000
                if crime_id != 0:
                    return crime_id
            except Exception:
                pass
        # Fallback to ZaporednaStevilkaKD
        try:
            return int(row["ZaporednaStevilkaKD"])
        except Exception:
            return None

    df_all["CrimeID"] = df_all.apply(_get_crime_id, axis=1)

    # Whether this person entry is an 'ovaden' (accused). Derive from `VrstaOsebe`.
    df_all["IsOvad"] = df_all["VrstaOsebe"].astype(str).str.upper().str.contains("OVAD", na=False)

    # Keep existing sentence heuristic (may be empty for these data)
    df_all["IsSentenced"] = df_all["VrstaZakljucnegaDokumenta"].apply(_is_sentenced)

    # Reorder and save
    df_out = df_all[
        [
            "ZaporednaStevilkaOsebeVKD",
            "CrimeID",
            "VrstaOsebe",
            "VrstaZakljucnegaDokumenta",
            "LetoZakljucnegaDokumenta",
            "IsSentenced",
            "IsOvad",
        ]
    ].copy()

    df_out.to_csv(out_csv, index=False, quoting=1, encoding="utf-8")
    logger.info("Wrote person–crime relations: %s (%d rows)", out_csv, len(df_out))
    return df_out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    formatted = Path(__file__).parents[2] / "data" / "formatted"
    out = Path(__file__).parents[2] / "data" / "relations" / "person_relations.csv"
    build_relations(formatted, out)
