# FRI-PR-seminarska

## Setup
Clone project
```bash
git clone git@github.com:grobolsek/FRI-PR-seminarska.git
```

Install dependencies
```bash
pip install -e .
```

Install dependencies for development
```bash
pip install -e ".[dev]"
pre-commit install
```

## TODO

### 1. Formatting data

**Format** - preserve original data alongside cleaned versions; use functions/classes for modularity

- [ ] For columns with enum values, validate and fix incorrect values where possible; optionally group ranges (e.g. `0-5`) as a configurable argument
- [ ] For all columns, validate expected formats (e.g. `MesecStoritve` must match `(0?[1-9]|1[0-2])\.[12][0-9]{3}`)
- [ ] For all columns, replace unknown/missing values with `None`
- [ ] `OpisKD` - split into KZ code and description as separate fields
- [ ] `KriminalisticnaOznacba` and `UporabljenoSredstvo` - decide on representation: combined array, one row per attribute, or current format; investigate what `- O` means in `KriminalisticnaOznacba`
- [ ] Group similar crime types (e.g. theft and fraud) into higher-level categories

**Tables** - output as new separate tables, keep originals untouched

- [ ] `ZaporednaStevilkaOsebeVKD` encodes who was involved in each criminal act (e.g. multiple victims or perpetrators). Use it to determine the roles present (victim, criminal) and outcomes (e.g. whether the criminal was sentenced). Create a new relation table that captures these relationships so they can be queried and analyzed.
- [ ] `MesecStoritve` records when a criminal act was committed. Combine all files and split records into separate files by year of the crime. If we can assume the year of the source file corresponds to when prosecution ended or was abandoned, we can compute how long each prosecution lasted - or how long authorities were willing to pursue a case before dropping it. Cross-reference with `ZaporednaStevilkaOsebeVKD` to match people to outcomes.

**Normalizations** - return normalized table via a function/class based on the current analysis goal

- [ ] Normalize values per the dimension being analyzed (e.g. per-location normalization for geographic crime analysis)

---

### 2. Data usage

**Analysis**

- [ ] Correlate crimes with weather conditions and holidays
- [ ] Identify trends over the years
- [ ] Compare crime rates against [immigration statistics](https://www.gov.si/podrocja/drzava-in-druzba/priseljevanje-v-slovenijo/)

**Predictions**

- [ ] Given parameters (day, day of week, time, immigration, location, age, etc.), predict crime probability and type
- [ ] Forecast expected crimes for upcoming years; identify rising and declining crime trends
