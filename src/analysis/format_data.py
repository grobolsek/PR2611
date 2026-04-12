"""Data formatter."""

import logging
import pathlib

import pandas as pd

NA_VALLS = ["", "NI OZNAKE", "199-NI PREDMETA", "OSTALO"]
logger = logging.getLogger(__name__)


def format_data(input_file: pathlib.Path) -> pd.DataFrame:
    """Read a CSV file and return a cleaned DataFrame."""
    try:
        criminal_df = pd.read_csv(
            input_file.absolute(),
            sep=";",
            encoding="latin1",
            on_bad_lines="warn",
            engine="c",  # faster
            na_values=NA_VALLS,
        )

        filled_df = criminal_df.replace("BREZ", 0)  # denaran škoda
        return filled_df.fillna(-1)

    except (OSError, pd.errors.ParserError, ValueError) as e:
        logger.warning(f"Error processing {input_file.name}: {e}")
        return pd.DataFrame()


def format_data_all() -> None:
    """Process all raw CSV files and write formatted output to data/formatted."""
    base_path = pathlib.Path(__file__).parent.parent.parent

    input_dir = base_path / "data" / "raw"
    output_dir = base_path / "data" / "formated"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        logger.warning(f"{input_dir} not a dir!")
        return

    for file in input_dir.glob("*.csv"):
        formatted_df = format_data(file)
        save_path = output_dir / file.name
        formatted_df.to_csv(save_path, sep=";", index=False, quoting=1, encoding="utf-8")

        logger.info(f"Processed: {file.name} -> {save_path}")
