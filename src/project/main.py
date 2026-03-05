import pandas as pd  # noqa: D100

df: pd.DataFrame = pd.read_csv("kd2023.csv", delimiter=";", header=0, encoding="latin1")
print(df.head())  # noqa: T201
