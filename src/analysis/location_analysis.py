from pathlib import Path

import pandas as pd

from analysis.data_formatter import format_data_all
from analysis.population import get_population

YEAR = 2024


files: dict[int, Path] = {int(file.name[2:6]): file for file in format_data_all(force=True)}

CA_data = pd.read_csv(files[YEAR], quoting=1, encoding="cp1250")
print(CA_data)
population = get_population(YEAR, 1)

CA_data = CA_data[CA_data["VrstaOsebe"] == "OVADENI OSUMLJENEC"]
location_stats = (
    CA_data.groupby("PUStoritveKD")
    .agg(
        count=("PUStoritveKD", "count"),
    )
    .sort_values("count", ascending=False)
)

population_by_region = population.set_index("region")["sum"]
location_stats["population"] = location_stats.index.map(population_by_region.to_dict())

location_stats["percent"] = location_stats["count"] / CA_data.shape[0] * 100
location_stats["criminals in population"] = location_stats["count"] / location_stats["population"]
