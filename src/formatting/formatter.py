"""Formatting pipeline for raw crime-statistics CSV files.

Reads raw CSV files from ``data/raw``, applies a fixed sequence of
cleaning and normalization steps (defined in :mod:`analysis`), and writes
the results to ``data/formatted``.  No data is returned; the sole output
is the files written to disk.
"""

import logging
import pathlib

import pandas as pd

from formatting.formatting_functions import (
    add_crime_cluster,
    get_data,
    get_files,
    mask_values,
    melt_numbered_columns,
    normalize_columns,
    order_columns,
    repair_by_group,
    split_opis_kd,
    to_bool,
)

logger = logging.getLogger(__name__)

_BASE_PATH = pathlib.Path(__file__).parent.parent.parent


def _apply_pipeline(data: pd.DataFrame) -> pd.DataFrame:
    """Apply the full cleaning and normalisation pipeline to *data*.

    Steps (in order):
    1. Split ``OpisKD`` into a KZ code column and a description column.
    2. Convert flag columns to ``'DA'``/``'NE'``.
    3. Convert time/day/damage columns to ordered categoricals.
    4. Repair or drop rows with invalid ``MesecStoritve`` values.
    5. Melt numbered column groups into long format.
    6. Map crime descriptions to a high-level cluster label.
    7. Mask blank strings so they are treated as missing values.

    Args:
        data: Raw :class:`~pandas.DataFrame` read from a single CSV file.

    Returns:
        Cleaned and normalised :class:`~pandas.DataFrame`.
    """
    data = split_opis_kd(data, col="OpisKD", code_col="KodaKD", desc_col="OpisKDOpis")
    data = to_bool(
        data,
        {
            "GospodarskiKriminal": ["GOSPODARSKA"],
            "OrganiziranKriminal": ["ORGANIZIRANA"],
            "MladoletniskaKriminaliteta": ["MLADOLETNIŠKA"],
        },
    )
    data = order_columns(data, ["UraStoritve", "DanVTednu", "Skoda"])
    data = repair_by_group(
        data,
        col="MesecStoritve",
        group_col="ZaporednaStevilkaKD",
        pattern=r"(0?[1-9]|1[0-2])\.[12][0-9]{3}",
    )
    data = melt_numbered_columns(data, ["KriminalisticnaOznacba", "UporabljenoSredstvo"])
    data = add_crime_cluster(data, "OpisKDOpis")
    return mask_values(data, ["", " "])


def _save_by_crime_year(data: pd.DataFrame, by_year_dir: pathlib.Path, closing_year: int) -> None:
    """Split *data* by crime year and append each slice to its per-year CSV.

    Extracts the year from ``MesecStoritve`` (format ``MM.YYYY``), attaches a
    ``LetoZakljucka`` column with *closing_year* (the year encoded in the
    source filename), then appends each year's rows to
    ``<by_year_dir>/<year>.csv``.  Creates the file with a header if it does
    not yet exist; otherwise appends without repeating the header.

    Args:
        data: Cleaned DataFrame produced by :func:`_apply_pipeline`.
        by_year_dir: Directory where per-year CSV files are stored.
        closing_year: The year the source file covers (from the filename).
    """
    by_year_dir.mkdir(parents=True, exist_ok=True)

    data = data.copy()
    data["LetoZakljucka"] = closing_year

    # Derive crime year from MesecStoritve (format M.YYYY or MM.YYYY)
    crime_years = data["MesecStoritve"].astype(str).str.extract(r"\.(\d{4})$")[0]
    data["_LetoStoritve"] = pd.to_numeric(crime_years, errors="coerce")

    # Group integrity: if any row in a crime group has no parseable year, drop the whole group
    id_col = "ZaporednaStevilkaKD"
    bad_ids = data.loc[data["_LetoStoritve"].isna(), id_col].unique()
    if len(bad_ids):
        logger.warning(
            "%d crime group(s) had no parseable year in MesecStoritve and were dropped entirely.",
            len(bad_ids),
        )
        data = data[~data[id_col].isin(bad_ids)]

    for year, group in data.groupby("_LetoStoritve", dropna=True):
        year_int = int(year)  # type: ignore[arg-type]
        out_path = by_year_dir / f"{year_int}.csv"
        slice_ = group.drop(columns=["_LetoStoritve"]).copy()

        # Renumber crime IDs so they don't collide with IDs already in the file
        if out_path.exists():
            existing = pd.read_csv(out_path, usecols=[id_col], encoding="utf-8")
            max_id = int(existing[id_col].max())
        else:
            max_id = 0

        old_ids = sorted(slice_[id_col].unique())
        id_map = {old: max_id + rank for rank, old in enumerate(old_ids, start=1)}
        slice_[id_col] = slice_[id_col].map(id_map)

        # ZaporednaStevilkaOsebeVKD encodes crime_id * 1000 + person_seq_within_crime
        if "ZaporednaStevilkaOsebeVKD" in slice_.columns:
            person_seq = slice_["ZaporednaStevilkaOsebeVKD"] % 1000
            slice_["ZaporednaStevilkaOsebeVKD"] = slice_[id_col] * 1000 + person_seq

        write_header = not out_path.exists()
        slice_.to_csv(out_path, mode="a", index=False, header=write_header, quoting=1, encoding="utf-8")
        logger.info(
            "Appended %d rows for crime year %d -> %s (IDs %d-%d)",
            len(slice_),
            year_int,
            out_path.name,
            max_id + 1,
            max_id + len(old_ids),
        )


def format_file(input_file: pathlib.Path, output_file: pathlib.Path, by_year_dir: pathlib.Path) -> None:
    """Format a single raw CSV file, save the result, and split it by crime year.

    Reads *input_file*, runs the full cleaning pipeline, writes the complete
    formatted output to *output_file*, and additionally appends rows split by
    crime year into ``<by_year_dir>/<year>.csv``.  Does nothing if reading
    fails.

    Args:
        input_file: Path to the raw source CSV.
        output_file: Destination path for the full formatted CSV.
        by_year_dir: Directory where per-crime-year CSVs are maintained.
    """
    data = get_data(input_file)
    if data.empty:
        logger.warning("Skipping %s: could not read file.", input_file.name)
        return

    data = normalize_columns(data, input_file.name)
    data = _apply_pipeline(data)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output_file, index=False, quoting=1, encoding="utf-8")
    logger.info("Formatted: %s -> %s", input_file.name, output_file)

    closing_year_match = __import__("re").search(r"(\d{4})", input_file.stem)
    if closing_year_match is None:
        logger.warning("Could not extract year from filename %s; skipping by-year split.", input_file.name)
        return
    closing_year = int(closing_year_match.group(1))

    _save_by_crime_year(data, by_year_dir, closing_year)


def format_data_all(
    *,
    input_dir: pathlib.Path | None = None,
    output_dir: pathlib.Path | None = None,
    by_year_dir: pathlib.Path | None = None,
    year: int | str | list[int] | list[str] | None = None,
    force: bool = False,
) -> None:
    """Format all raw CSV files and write the results to *output_dir*.

    Iterates over CSV files in *input_dir* (optionally filtered by *year*),
    applies the full cleaning pipeline to each one, saves the complete output
    to *output_dir*, and appends rows split by crime year into *by_year_dir*.
    Already-formatted files are skipped unless *force* is ``True``.

    Args:
        input_dir: Directory containing raw CSV files. Defaults to ``data/raw``
            relative to the project root.
        output_dir: Directory for formatted output. Defaults to
            ``data/formatted`` relative to the project root.
        by_year_dir: Directory for per-crime-year CSVs. Defaults to
            ``data/by_year`` relative to the project root.
        year: Year(s) used to filter input files by name. Pass ``None`` to
            process every CSV in *input_dir*.
        force: Re-format files that already exist in *output_dir* when
            ``True``; skip them when ``False`` (default).
    """
    if input_dir is None:
        input_dir = _BASE_PATH / "data" / "raw"
    if output_dir is None:
        output_dir = _BASE_PATH / "data" / "formatted"
    if by_year_dir is None:
        by_year_dir = _BASE_PATH / "data" / "by_year"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        raise NotADirectoryError(input_dir)

    files = get_files(input_dir, year=year)
    total = len(files)
    done = 0
    skipped = 0

    for input_file in files:
        output_file = output_dir / input_file.name

        if not force and output_file.exists():
            skipped += 1
            logger.info("[%d/%d] Skipping (already formatted): %s", skipped + done, total, input_file.name)
            continue

        done += 1
        logger.info("[%d/%d] Processing: %s", done + skipped, total, input_file.name)
        format_file(input_file, output_file, by_year_dir)

    logger.info("Done: %d processed, %d skipped, %d total.", done, skipped, total)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    format_data_all(input_dir=pathlib.Path("data/raw"))
