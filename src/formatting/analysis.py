"""This program if for analyzing data for formatting."""

import logging
import re
from pathlib import Path

import pandas as pd

NA_VALLS = ["", "NI OZNAKE", "199-NI PREDMETA", "OSTALO"]
logger = logging.getLogger(__name__)


def get_files(directory: Path, *, year: int | str | list[int] | list[str] | None = None) -> list[Path]:
    """Return CSV files in *directory*, optionally filtered by year.

    Args:
        directory: Directory to search for CSV files.
        year: Year(s) to filter by. A file is included if its name contains
              any of the provided years as a substring. Pass ``None`` to
              return all CSV files.

    Returns:
        List of matching :class:`~pathlib.Path` objects.

    Raises:
        NotADirectoryError: If *directory* does not exist or is not a directory.
    """
    directory = directory.resolve()

    if not directory.is_dir():
        raise NotADirectoryError(directory)

    if year is None:
        return list(directory.glob("*.csv"))

    years = year if isinstance(year, list) else [year]
    pattern = "|".join(map(re.escape, map(str, years)))
    return [file for file in directory.glob("*.csv") if re.search(pattern, file.name)]


def get_data(input_file: Path) -> pd.DataFrame:
    """Read a CSV file and return DataFrame."""
    try:
        return pd.read_csv(
            input_file.absolute(),
            sep=";",
            encoding="cp1250",
            on_bad_lines="warn",
            engine="c",  # faster
            na_values=NA_VALLS,
        )

    except (OSError, pd.errors.ParserError, ValueError) as e:
        logger.warning(f"Error processing {input_file.name}: {e}")
        return pd.DataFrame()


def unique_values(
    data: pd.DataFrame,
    *,
    exclude: list[str | int] | None = None,
) -> dict[str, list]:
    """Return and log unique non-null values for each column.

    Args:
        data: Input DataFrame.
        exclude: Column names or integer positions to skip. Defaults to ``None``.
    """
    excluded = set()
    for item in exclude or []:
        if isinstance(item, int):
            excluded.add(data.columns[item])
        else:
            excluded.add(item)

    def _sort(series: pd.Series) -> list:
        vals = series.dropna().unique()
        if isinstance(series.dtype, pd.CategoricalDtype) and series.dtype.ordered:
            cats = list(series.cat.categories)
            return sorted(vals.tolist(), key=cats.index)
        return sorted(vals.tolist())

    result = {col: _sort(data[col]) for col in data.columns if col not in excluded}
    for col, vals in result.items():
        logger.info("%s: %s", col, vals)
    return result


def to_bool(
    data: pd.DataFrame,
    columns: list[str] | dict[str, list[str]],
) -> pd.DataFrame:
    """Convert flag columns to 'DA'/'NE'.

    When `columns` is a list, a cell is mapped to 'DA' if it contains a
    non-whitespace value, otherwise 'NE'.

    When `columns` is a dict mapping column name to a list of values that
    count as 'DA', only those exact values (after stripping) produce 'DA';
    everything else (including NaN and whitespace-only strings) produces 'NE'.

    Args:
        data: Input DataFrame.
        columns: Column names to convert, or a dict of column → DA values.

    Returns:
        DataFrame with the specified columns replaced by 'DA'/'NE' values.
    """
    data = data.copy()
    if isinstance(columns, dict):
        for col, da_values in columns.items():
            da_set = {str(v).strip() for v in da_values}
            data[col] = data[col].apply(
                lambda v, s=da_set: "DA" if not pd.isna(v) and str(v).strip() in s else "NE",
            )
    else:
        for col in columns:
            data[col] = data[col].apply(
                lambda v: "NE" if pd.isna(v) or str(v).strip() == "" else "DA",
            )
    return data


_DAN_V_TEDNU_ORDER = ["PONEDELJEK", "TOREK", "SREDA", "ČETRTEK", "PETEK", "SOBOTA", "NEDELJA"]

_SKODA_ORDER = [
    "BREZ",
    "DO 100 EUR",
    "100 - 1.000 EUR",
    "1.000 - 10.000 EUR",
    "10.000 - 100.000 EUR",
    "100.000 - 500.000 EUR",
    "NAD 500.000 EUR",
]


def order_columns(data: pd.DataFrame, columns: list[str] | dict[str, list[str]]) -> pd.DataFrame:
    """Convert columns to ordered categoricals.

    When `columns` is a list, time-range columns (e.g. 'UraStoritve') are
    sorted by parsing the start hour; 'DanVTednu' uses weekday order;
    'Skoda' uses damage-range order. Unknown column names fall back to
    lexicographic order.

    When `columns` is a dict mapping column name to an explicit ordered list,
    that order is used directly.

    Args:
        data: Input DataFrame.
        columns: Column names to order, or a dict of column → ordered values.

    Returns:
        DataFrame with the specified columns converted to ordered Categorical.
    """
    data = data.copy()

    if isinstance(columns, dict):
        for col, order in columns.items():
            data[col] = pd.Categorical(data[col], categories=order, ordered=True)
        return data

    for col in columns:
        col_lower = col.lower()
        if col_lower == "danvtednu":
            order = _DAN_V_TEDNU_ORDER
        elif col_lower == "skoda":
            order = _SKODA_ORDER
        else:
            # Assume time-range strings like 'HH:MM-HH:MM'; sort by start hour
            unique_vals = sorted(
                data[col].dropna().unique(),
                key=lambda v: int(str(v).split(":")[0]) if str(v)[0:2].isdigit() else str(v),
            )
            order = list(unique_vals)
        data[col] = pd.Categorical(data[col], categories=order, ordered=True)

    return data


def melt_numbered_columns(
    data: pd.DataFrame,
    prefixes: list[str],
) -> pd.DataFrame:
    """Melt numbered column groups into long format.

    For each prefix (e.g. 'KriminalisticnaOznacba'), all columns matching
    ``<prefix>1``, ``<prefix>2``, ... are melted into a single column named
    ``<prefix>``. Rows with no value across all numbered columns are dropped.
    The original numbered columns are removed.

    Args:
        data: Input DataFrame.
        prefixes: Column-name prefixes to melt (e.g. ['KriminalisticnaOznacba', 'UporabljenoSredstvo']).

    Returns:
        Long-format DataFrame with one row per non-null value per prefix group.
    """
    id_cols = [c for c in data.columns if not any(c.startswith(p) for p in prefixes)]

    frames = []
    for prefix in prefixes:
        value_cols = sorted(c for c in data.columns if c.startswith(prefix) and c[len(prefix) :].isdigit())
        if not value_cols:
            logger.warning("melt_numbered_columns: no columns found for prefix %r", prefix)
            continue
        melted = (
            data[id_cols + value_cols]
            .melt(
                id_vars=id_cols,
                value_vars=value_cols,
                var_name="_src",
                value_name=prefix,
            )
            .dropna(subset=[prefix])
        )
        melted = melted.drop(columns=["_src"]).reset_index(drop=True)
        frames.append(melted)

    if not frames:
        return data

    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=id_cols, how="outer")

    return result.reset_index(drop=True)


def split_opis_kd(
    data: pd.DataFrame,
    col: str,
    code_col: str,
    desc_col: str,
) -> pd.DataFrame:
    """Split a combined KZ-code + description column into two separate columns.

    Expects values in the form ``KZxx/... - DESCRIPTION``. The code is
    everything before the first `` - ``, the description is everything after.
    If the separator is absent the original value is placed in `desc_col`
    and `code_col` is left as NaN.

    Args:
        data: Input DataFrame.
        col: Source column to split.
        code_col: Name for the new KZ-code column.
        desc_col: Name for the new description column.

    Returns:
        DataFrame with `col` replaced by `code_col` and `desc_col`.
    """
    data = data.copy()
    split = data[col].str.split(r" - ", n=1, expand=True)
    col_idx = int(data.columns.get_loc(col))  # type: ignore[arg-type]

    if split.shape[1] == 2:  # noqa: PLR2004
        data.insert(col_idx, code_col, split[0])
        data.insert(col_idx + 1, desc_col, split[1])
    else:
        data.insert(col_idx, code_col, None)
        data.insert(col_idx + 1, desc_col, split[0])

    return data.drop(columns=[col])


def repair_by_group(
    data: pd.DataFrame,
    col: str,
    group_col: str,
    pattern: str,
) -> pd.DataFrame:
    """Fill invalid values in `col` from other rows in the same group, or drop the group.

    For each group (identified by `group_col`):
    - Rows whose `col` value matches `pattern` are considered valid.
    - Rows with an invalid value are filled with the valid value from the group
      (if all valid rows agree on one value).
    - If the group has no valid value at all, all rows in the group are dropped.

    Args:
        data: Input DataFrame.
        col: Column to repair.
        group_col: Column that identifies the group.
        pattern: Full-match regex for a valid value.

    Returns:
        Repaired DataFrame with invalid-only groups removed.
    """
    compiled = re.compile(r"^(?:" + pattern + r")$")

    def _valid(v: object) -> bool:
        if v is None or (isinstance(v, float) and v.__class__.__mro__[0] is float and str(v) == "nan"):
            return False
        return bool(compiled.match(str(v)))

    data = data.copy()
    keep_mask = pd.Series(data=True, index=data.index)
    fixed_rows = 0

    for _, group in data.groupby(group_col, sort=False):
        valid_vals = group[col][group[col].apply(_valid)].unique()
        if len(valid_vals) == 0:
            keep_mask[group.index] = False
        elif len(valid_vals) == 1:
            fill_val = valid_vals[0]
            invalid_rows = group.index[~group[col].apply(_valid)]
            data.loc[invalid_rows, col] = fill_val
            fixed_rows += len(invalid_rows)
        # if multiple different valid values exist, leave as-is (ambiguous)

    dropped = int((~keep_mask).sum())
    total = fixed_rows + dropped
    pct = f"{fixed_rows / total * 100:.1f}%" if total else "N/A"
    print(f"repair_by_group [{col}]: fixed {fixed_rows}, removed {dropped} ({pct} success rate)")
    return data[keep_mask].reset_index(drop=True)


_COLUMN_PATTERNS: dict[str, str] = {
    "MesecStoritve": r"(0?[1-9]|1[0-2])\.[12][0-9]{3}",
    "UraStoritve": r"(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]-(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]",
    "DanVTednu": r"PONEDELJEK|TOREK|SREDA|ČETRTEK|PETEK|SOBOTA|NEDELJA",
    "Skoda": r"BREZ|DO 100 EUR|100 - 1\.000 EUR|1\.000 - 10\.000 EUR|10\.000 - 100\.000 EUR|100\.000 - 500\.000 EUR|NAD 500\.000 EUR",
    "GospodarskiKriminal": r"DA|NE",
    "OrganiziranKriminal": r"DA|NE",
    "MladoletniskaKriminaliteta": r"DA|NE",
}


def validate_formats(
    data: pd.DataFrame,
    patterns: dict[str, str] | None = None,
) -> dict[str, list]:
    """Check columns against expected regex patterns and report invalid values.

    Args:
        data: Input DataFrame.
        patterns: Dict of column → full-match regex. Defaults to ``_COLUMN_PATTERNS``.

    Returns:
        Dict mapping column name to a list of (row_index, value) tuples that
        failed validation. Columns with no violations are omitted.
    """
    if patterns is None:
        patterns = _COLUMN_PATTERNS

    violations: dict[str, list] = {}
    for col, pattern in patterns.items():
        if col not in data.columns:
            logger.warning("validate_formats: column %r not found in DataFrame", col)
            continue
        compiled = re.compile(r"^(?:" + pattern + r")$")
        bad = [(idx, val) for idx, val in data[col].dropna().items() if not compiled.match(str(val))]
        if bad:
            violations[col] = bad
            logger.warning(
                "validate_formats: %d invalid value(s) in %r: %s",
                len(bad),
                col,
                bad[:5],
            )
        else:
            logger.info("validate_formats: %r OK", col)

    return violations


files = get_files(Path("data/raw"), year=2024)

data = get_data(files[0])
data = split_opis_kd(data, col="OpisKD", code_col="KodaKD", desc_col="OpisKDOpis")
data = to_bool(
    data,
    {"GospodarskiKriminal": ["GOSPODARSKA"], "OrganiziranKriminal": ["ORGANIZIRANA"], "MladoletniskaKriminaliteta": ["MLADOLETNIŠKA"]},
)
data = order_columns(data, ["UraStoritve", "DanVTednu", "Skoda"])
data = repair_by_group(
    data,
    col="MesecStoritve",
    group_col="ZaporednaStevilkaKD",
    pattern=r"(0?[1-9]|1[0-2])\.[12][0-9]{3}",
)
data = melt_numbered_columns(data, ["KriminalisticnaOznacba", "UporabljenoSredstvo"])

# violations = validate_formats(data)
# for col, bad in violations.items():
#     counts: dict = {}
#     for _, val in bad:
#         counts[val] = counts.get(val, 0) + 1
#     print(f"{col}:")
#     for val, count in sorted(counts.items(), key=lambda x: -x[1]):
#         print(f"  {val!r}: {count}x")
#

CRIME_CLUSTERS = {
    "Nasilje nad osebami": [
        "UBOJ",
        "UMOR",
        "UGRABITEV",
        "UGRABITEV IN PRISILNO IZGINOTJE",
        "HUDA TELESNA POŠKODBA",
        "POSEBNO HUDA TELESNA POŠKODBA",
        "LAHKA TELESNA POŠKODBA",
        "MUČENJE",
        "NASILJE V DRUŽINI",
        "NASILNIŠTVO",
        "PRISILJENJE",
        "GROŽNJA",
        "PROTIPRAVEN ODVZEM PROSTOSTI",
        "OGROŽANJE Z NEVARNIM ORODJEM PRI PRETEPU ALI PREPIRU",
        "SODELOVANJE PRI PRETEPU",
        "NAPELJEVANJE K SAMOMORU IN POMOČ PRI SAMOMORU",
        "ZANEMARJANJE MLADOLETNE OSEBE IN SUROVO RAVNANJE",
        "ZAPUSTITEV SLABOTNE OSEBE",
        "NEODVRNITEV NEVARNOSTI",
        "OPUSTITEV POMOČI",
        "ODVZEM MLADOLETNE OSEBE",
    ],
    "Spolna kazniva dejanja": [
        "POSILSTVO",
        "SPOLNO NASILJE",
        "SPOLNA ZLORABA SLABOTNE OSEBE",
        "SPOLNI NAPAD NA OSEBO MLAJŠO OD 14 LET",
        "SPOLNI NAPAD NA OSEBO,MLAJŠO OD PETNAJST LET",
        "KRŠITEV SPOLNE NEDOTAKLJIVOSTI Z ZLORABO POLOŽAJA",
        "PRIDOBIVANJE OSEB, MLAJŠIH OD PETNAJST LET, ZA SPOLE NAMENE",
        "PRIKAZOVANJE, IZDELAVA, POSEST IN POSREDOVANJE PORNOGRAFSKEGA GRADIVA",
        "ZLORABA PROSTITUCIJE",
    ],
    "Premoženjska kazniva dejanja": [
        "TATVINA",
        "VELIKA TATVINA",
        "ROPARSKA TATVINA",
        "ROP",
        "GOLJUFIJA",
        "POSLOVNA GOLJUFIJA",
        "GOLJUFIJA NA ŠKODO EVROPSKE UNIJE",
        "IZNEVERJENJE",
        "IZSILJEVANJE",
        "ZATAJITEV",
        "PONEVERBA IN NEUPRAVIČENA UPORABA TUJEGA PREMOŽENJA",
        "POŠKODOVANJE TUJE STVARI",
        "SAMOVOLJNOST",
        "PROTIPRAVNO ZAVZETJE NEPREMIČNINE",
        "ODVZEM MOTORNEGA VOZILA",
        "ODERUŠTVO",
        "OŠKODOVANJE TUJIH PRAVIC",
        "PRESLEPITEV PRI PRIDOBITVI IN UPORABI POSOJILA ALI UGODNOSTI",
    ],
    "Gospodarska in finančna kazniva dejanja": [
        "DAVČNA ZATAJITEV",
        "PRANJE DENARJA",
        "PONAREJANJE DENARJA",
        "PONAREJANJE IN UPORABA PONAREJENIH VREDNOTNIC ALI VREDNOSTNIH PAPIRJEV",
        "ZLORABA POLOŽAJA ALI ZAUPANJA PRI GOSPODARSKI DEJAVNOSTI",
        "ZLORABA TRGA FINANČNIH INSTRUMENTOV",
        "OŠKODOVANJE JAVNIH SREDSTEV",
        "OŠKODOVANJE UPNIKOV",
        "OŠKODOVANJE UPNIKOV Z GOLJUFIJO ALI NEVESTNIM POSLOVANJEM",
        "DAJANJE PREDNOSTI UPNIKOM",
        "POVZROČITEV STEČAJA Z GOLJUFIJO ALI NEVESTNIM POSLOVANJEM",
        "PROTIPRAVNO OMEJEVANJE KONKURENCE",
        "ORGANIZIRANJE DENARNIH VERIG IN NEDOVOLJENO PRIREJANJE IGER NA SREČO",
        "ORGANIZIRANJE DENARNIH VERIG,NEDOVOLJENO PRIREJANJE IGER NA SREČO IN NEDOVOLJENO PRIREJANJE REZULTAT",
        "ZLORABA NEGOTOVINSKEGA PLAČILNEGA SREDSTVA",
        "UPORABA PONAREJENEGA NEGOTOVINSKEGA PLAČILNEGA SREDSTVA",
        "ZAPOSLOVANJE NA ČRNO",
    ],
    "Korupcija in podkupovanje": [
        "JEMANJE PODKUPNINE",
        "DAJANJE PODKUPNINE",
        "DAJANJE DARIL ZA NEZAKONITO POSREDOVANJE",
        "SPREJEMANJE KORISTI ZA NEZAKONITO POSREDOVANJE",
        "NEDOVOLJENO DAJANJE DARIL",
        "NEDOVOLJENO SPREJEMANJE DARIL",
        "MAZAŠTVO",
    ],
    "Zloraba uradnega položaja in oviranje pravosodja": [
        "ZLORABA URADNEGA POLOŽAJA ALI URADNIH PRAVIC",
        "KRŠITEV ČLOVEŠKEGA DOSTOJANSTVA Z ZLORABO URADNEGA POLOŽAJA ALI URADNIH PRAVIC",
        "ZLORABA IZVRŠBE",
        "NEVESTNO DELO V SLUŽBI",
        "KRIVA IZPOVEDBA",
        "KRIVA OVADBA",
        "OVIRANJE PRAVOSODNIH IN DRUGIH DRŽAVNIH ORGANOV",
        "PREPREČITEV DOKAZOVANJA",
        "PREPREČITEV URADNEGA DEJANJA ALI MAŠČEVANJE URADNI OSEBI",
        "PROTIZAKONITO, PRISTRANSKO IN KRIVIČNO SOJENJE",
        "LAŽNO IZDAJANJE ZA URADNO ALI VOJAŠKO OSEBO",
        "POMOČ STORILCU PO STORITVI KAZNIVEGA DEJANJA",
        "PRIKRIVANJE",
        "OVERITEV LAŽNE VSEBINE",
        "OMOGOČANJE BEGA OSEBI, KI JI JE VZETA PROSTOST",
        "ODSTRANITEV ALI POŠKODOVANJE URADNEGA PEČATA ALI ZNAMENJA",
        "ODVZEM ALI UNIČENJE URADNEGA PEČATA ALI URADNIH SPISOV",
        "KRŠITEV TAJNOSTI POSTOPKA",
    ],
    "Ponarejanje in listine": [
        "PONAREJANJE LISTIN",
        "PONAREDITEV ALI UNIČENJE POSLOVNIH LISTIN",
        "PONAREDITEV ALI UNIČENJE URADNE LISTINE, KNJIGE, SPISA ALI ARHIVSKEGA GRADIVA",
        "POSEBNI PRIMERI PONAREJANJA LISTIN",
        "PONAREJANJE ZNAMENJ ZA ZAZNAMOVANJE BLAGA, MER IN UTEŽI",
        "IZDELAVA,PRIDOBITEV IN ODTUJITEV PRIPOMOČKOV ZA PONAREJANJE",
        "IZDAJA IN UPORABA LAŽNEGA ZDRAVNIŠKEGA ALI VETERINARSKEGA SPRIČEVALA",
    ],
    "Droge, orožje in javna varnost": [
        "NEUPRAVIČENA PROIZVODNJA IN PROMET S PREPOVEDANIMI DROGAMI, NEDOVOLJENIMI SNOVMI IN POSTOPKI V ŠPORT",
        "OMOGOČANJE UŽIVANJA ALI UPORABE PREPOVEDANIH DROG ALI NEDOVOLJENIH SNOVI ALI POSTOPKOV V ŠPORTU",
        "NEDOVOLJENA PROIZVODNJA IN PROMET OROŽJA ALI EKSPLOZIVA",
        "IZDELOVANJE IN PRIDOBIVANJE OROŽJA IN PRIPOMOČKOV, NAMENJENIH ZA KAZNIVO DEJANJE",
        "PROIZVODNJA IN PROMET ŠKODLJIVIH SREDSTEV ZA ZDRAVLJENJE",
        "ONESNAŽENJE PITNE VODE",
        "ONESNAŽENJE ŽIVIL ALI KRME",
        "POVZROČITEV SPLOŠNE NEVARNOSTI",
        "POŽIG",
        "POŠKODOVANJE ALI UNIČENJE JAVNIH NAPRAV",
        "POVZROČITEV NEVARNOSTI PRI GRADBENI DEJAVNOSTI",
        "ZLORABA ZNAMENJ ZA POMOČ IN NEVARNOST",
    ],
    "Kazniva dejanja v prometu": [
        "NEVARNA VOŽNJA V CESTNEM PROMETU",
        "POVZROČITEV PROMETNE NESREČE IZ MALOMARNOSTI",
        "POVZROČITEV SMRTI IZ MALOMARNOSTI",
        "OGROŽANJE JAVNEGA PROMETA Z NEVARNIM DEJANJEM ALI SREDSTVOM",
        "OGROŽANJE POSEBNIH VRST JAVNEGA PROMETA",
        "OPUSTITEV NADZORSTVA V JAVNEM PROMETU",
        "ZAPUSTITEV POŠKODOVANCA V PROMETNI NESREČI BREZ POMOČI",
    ],
    "Okolje, narava in živali": [
        "OBREMENJEVANJE IN UNIČEVANJE OKOLJA",
        "OGROŽANJE OKOLJA S HRUPOM ALI SVETLOBO",
        "UNIČEVANJE GOZDOV",
        "NEZAKONITO RAVNANJE Z ZAŠČITENIMI ŽIVALMI IN RASTLINAMI",
        "NEZAKONIT LOV",
        "MUČENJE ŽIVALI",
        "PRENAŠANJE KUŽNIH BOLEZNI PRI ŽIVALIH IN",
        "POŠKODOVANJE ALI UNIČENJE STVARI, KI SO POSEBNEGA KULTURNEGA POMENA ALI NARAVNE VREDNOTE",
        "POŠKODOVANJE,ODSTRANITEV ALI UNIČENJE STVARI,KI SO POSEBNEGA KULTURNEGA POMENA ALI NARAVNE VREDNOTE",
    ],
    "Terorizem in organiziran kriminal": [
        "TERORIZEM",
        "NOVAČENJE IN USPOSABLJANJE ZA TERORIZEM",
        "ŠČUVANJE K NASILNI SPREMEMBI USTAVNE UREDITVE",
        "HUDODELSKO ZDRUŽEVANJE",
        "DOGOVOR ZA KAZNIVO DEJANJE",
        "SODELOVANJE V SKUPINI, KI STORI KAZNIVO DEJANJE",
        "JAVNO SPODBUJANJE SOVRAŠTVA, NASILJA ALI NESTRPNOSTI",
        "NAPAD NA URADNO OSEBO, KO OPRAVLJA NALOGE VARNOSTI",
        "TIHOTAPSTVO",
        "PREPOVEDANO PREHAJANJE MEJE ALI OZEMLJA DRŽAVE",
        "TRGOVINA Z LJUDMI",
    ],
    "Zasebnost, čast in komunikacije": [
        "OBREKOVANJE",
        "OPRAVLJANJE",
        "RAZŽALITEV",
        "ŽALJIVA OBDOLŽITEV",
        "OČITANJE KAZNIVEGA DEJANJA Z NAMENOM ZANIČEVANJA",
        "KRŠITEV NEDOTAKLJIVOSTI STANOVANJA",
        "KRŠITEV TAJNOSTI OBČIL",
        "NEUPRAVIČENO PRISLUŠKOVANJE IN ZVOČNO SNEMANJE",
        "NEUPRAVIČENO SLIKOVNO SNEMANJE",
        "ZLORABA OSEBNIH PODATKOV",
        "ZALEZOVANJE",
        "NEUPRAVIČENA OSEBNA PREISKAVA",
    ],
    "Delavske in socialne pravice": [
        "KRŠITEV TEMELJNIH PRAVIC DELAVCEV",
        "KRŠITEV PRAVIC DO SODELOVANJA PRI UPRAVLJANJU IN KRŠITEV SINDIKALNIH PRAVIC",
        "KRŠITEV PRAVIC IZ SOCIALNEGA ZAVAROVANJA",
        "PREPREČITEV VRNITVE NA DELO",
        "ŠIKANIRANJE NA DELOVNEM MESTU",
        "ZLORABA PRAVIC IZ SOCIALNEGA ZAVAROVANJA",
        "OGROŽANJE VARNOSTI PRI DELU",
        "NEPLAČEVANJE PREŽIVNINE",
    ],
    "Zdravje in medicina": [
        "MALOMARNO ZDRAVLJENJE IN OPRAVLJANJE ZDRAVILSKE DEJAVNOSTI",
        "NEVESTNA VETERINARSKA POMOČ",
        "OPUSTITEV ZDRAVSTVENE POMOČI",
        "PRENAŠANJE NALEZLJIVIH BOLEZNI",
    ],
    "Intelektualna lastnina in skrivnosti": [
        "KRŠITEV MATERIALNIH AVTORSKIH PRAVIC",
        "KRŠITEV MORALNIH AVTORSKIH PRAVIC",
        "NEUPRAVIČENA UPORABA TUJE OZNAKE ALI MODELA",
        "IZDAJA IN NEUPRAVIČENA PRIDOBITEV POSLOVNE SKRIVNOSTI",
        "NEUPRAVIČENA IZDAJA POKLICNE SKRIVNOSTI",
        "IZDAJA TAJNIH PODATKOV",
    ],
    "Kibernetska kazniva dejanja": [
        "NAPAD NA INFORMACIJSKI SISTEM",
        "ZLORABA INFORMACIJSKEGA SISTEMA",
    ],
    "Človekove pravice in volitve": [
        "KRŠITEV ENAKOPRAVNOSTI",
        "KRŠITEV PROSTE ODLOČITVE VOLIVCEV",
        "KRŠITEV PRAVICE DO PRAVNEGA SREDSTVA ALI PETICIJE",
        "KRŠITEV OMEJEVALNIH UKREPOV",
        "ZLORABA VOLILNE PRAVICE",
        "UNIČENJE ALI PONAREDITEV VOLILNIH LISTIN",
        "NEZAKONITO DAJANJE PRAVNE POMOČI",
    ],
    "Ostalo": [
        "SKRUNITEV TRUPLA",
        "OVIRANJE POGREBA IN SKRUNITEV GROBA",
        "SPREMEMBA RODBINSKEGA STANJA",
        "POŠKODOVANJE TUJE STVARI",
    ],
}


def add_crime_cluster(df: pd.DataFrame, crime_col: str) -> pd.DataFrame:
    # Build reverse mapping: crime -> cluster
    crime_to_cluster = {crime: cluster for cluster, crimes in CRIME_CLUSTERS.items() for crime in crimes}

    df = df.copy()
    df["KD_SKUPINA"] = df[crime_col].map(crime_to_cluster).fillna("Neznano")
    return df


def check_unmapped(df: pd.DataFrame, crime_col: str) -> list[str]:
    known = {crime for crimes in CRIME_CLUSTERS.values() for crime in crimes}
    return sorted(df[crime_col].dropna().unique()[~pd.Index(df[crime_col].dropna().unique()).isin(known)].tolist())


def mask_values(df: pd.DataFrame, values: list[str], columns: list[str] | None = None) -> pd.DataFrame:
    """Set DataFrame values to None if they appear in the given list.

    Args:
        df: Input DataFrame.
        values: List of values to replace with None.
        columns: Columns to apply masking to. Defaults to all columns.

    Returns:
        DataFrame with matching values replaced by None.
    """
    if columns is None:
        columns = df.columns.tolist()
    df[columns] = df[columns].apply(lambda col: col.where(~col.isin(values)))
    return df


data = add_crime_cluster(data, "OpisKDOpis")
data = mask_values(data, ["", " "])
