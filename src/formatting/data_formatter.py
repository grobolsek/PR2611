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
            encoding="cp1250",
            on_bad_lines="warn",
            engine="c",  # faster
            na_values=NA_VALLS,
        )

        return criminal_df.replace("BREZ", 0)  # denaran škoda

    except (OSError, pd.errors.ParserError, ValueError) as e:
        logger.warning(f"Error processing {input_file.name}: {e}")
        return pd.DataFrame()


def format_data_all(
    *,
    input_dir: pathlib.Path | None = None,
    output_dir: pathlib.Path | None = None,
    force: bool = False,
) -> list[pathlib.Path]:
    """Process all raw CSV files and write formatted output to data/formatted.

    Args:
        input_dir: Directory containing raw CSV files. Defaults to data/raw.
        output_dir: Directory to write formatted files. Defaults to data/formatted.
        force: If True, re-format files even if already present in output dir.

    Returns:
        list[pathlib.Path]: list of paths where new formatted files are saved.
    """
    files: list[pathlib.Path] = []

    base_path = pathlib.Path(__file__).parent.parent.parent

    if input_dir is None:
        input_dir = base_path / "data" / "raw"
    if output_dir is None:
        output_dir = base_path / "data" / "formatted"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        raise NotADirectoryError({input_dir})

    for file in input_dir.glob("*.csv"):
        save_path = output_dir / file.name

        if not force and save_path.exists():
            logger.info(f"Skipping (already formatted): {file.name}")
            files.append(save_path)
            continue

        formatted_df = format_data(file)
        formatted_df.to_csv(save_path, index=False, quoting=1, encoding="cp1250")

        files.append(save_path)
        logger.info(f"Processed: {file.name} -> {save_path}")

    return files
