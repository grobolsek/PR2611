"""Get population data by location using SiStat API.

This module fetches population counts (male, female, total) per statistical region
from the Slovenian statistical office (SiStat) API.
"""

import pandas as pd
import requests

API_URL = "https://pxweb.stat.si:443/SiStatData/api/v1/sl/Data/05C2006S.px"

# Age groups that together cover all ages without overlap:
# "4" = 0-14, "9" = 15-64, "10" = 65+
AGE_GROUPS = ["4", "9", "10"]


def get_population(year: int, half_year: int) -> pd.DataFrame:
    """Fetch population counts (male, female, total) per statistical region from SiStat.

    Args:
        year:       e.g. 2025
        half_year:  1 (as of Jan 1) or 2 (as of Jul 1)

    Returns:
        DataFrame with columns: region, male, female, total
    """
    period = f"{year}H{half_year}"

    payload = {
        "query": [
            {
                "code": "SPOL",
                "selection": {
                    "filter": "item",
                    "values": ["1", "2"],  # 1=male, 2=female
                },
            },
            {
                "code": "POLLETJE",
                "selection": {
                    "filter": "item",
                    "values": [period],
                },
            },
            {
                "code": "STAROST",
                "selection": {
                    "filter": "item",
                    "values": AGE_GROUPS,
                },
            },
        ],
        "response": {"format": "json-stat"},
    }

    response = requests.post(API_URL, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Parse json-stat response
    ds = data["dataset"]
    dims = ds["dimension"]
    values = ds["value"]

    # Dimension order and sizes
    dim_ids = dims["id"]  # e.g. ["SPOL", "STATISTIČNA REGIJA", "POLLETJE", "STAROST"]
    dim_sizes = dims["size"]

    def get_labels(dim_id: str) -> list:
        cat = dims[dim_id]["category"]
        # Return labels ordered by their position in the data
        index_map = cat["index"]  # {code: position}
        labels = cat["label"]  # {code: name}
        ordered = sorted(index_map.items(), key=lambda x: x[1])
        return [labels[k] for k, _ in ordered]

    region_labels = get_labels("STATISTIČNA REGIJA")  # ["SLOVENIJA", "Pomurska", ...]
    n_region = dim_sizes[dim_ids.index("STATISTIČNA REGIJA")]
    n_half = dim_sizes[dim_ids.index("POLLETJE")]
    n_age = dim_sizes[dim_ids.index("STAROST")]

    # Values are laid out as: SPOL | REGIJA | POLLETJE | STAROST
    def idx(i_sex: int, i_region: int, i_half: int, i_age: int) -> int:
        return i_sex * (n_region * n_half * n_age) + i_region * (n_half * n_age) + i_half * n_age + i_age

    rows = []
    for i_reg, region in enumerate(region_labels):
        male = sum(values[idx(0, i_reg, 0, a)] for a in range(n_age))
        female = sum(values[idx(1, i_reg, 0, a)] for a in range(n_age))
        rows.append(
            {
                "region": region,
                "male": male,
                "female": female,
                "sum": male + female,
            },
        )

    population_df = pd.DataFrame(rows).iloc[1:, :]
    return _rename_location(population_df)


def _rename_location(ca_data: pd.DataFrame) -> pd.DataFrame:
    region_to_pu = {
        "Pomurska": "PU MURSKA SOBOTA",
        "Podravska": "PU MARIBOR",
        "Koroška": "PU CELJE",
        "Savinjska": "PU CELJE",
        "Zasavska": "PU LJUBLJANA",
        "Posavska": "PU NOVO MESTO",
        "Jugovzhodna Slovenija": "PU NOVO MESTO",
        "Osrednjeslovenska": "PU LJUBLJANA",
        "Gorenjska": "PU KRANJ",
        "Primorsko-notranjska": "PU KOPER",
        "Goriška": "PU NOVA GORICA",
        "Obalno-kraška": "PU KOPER",
    }

    ca_data["region"] = ca_data["region"].map(region_to_pu)
    return ca_data.groupby("region", as_index=False)[["male", "female", "sum"]].sum()
