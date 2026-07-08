# Country Risk Reproduction Correlations

This repository checks whether separately downloaded NLA country-risk CSVs reproduce the paper-based country-risk panel distributed as `FirmCountryQuarter_withexposure.dta`.

The validation compares the DTA's firm-country-quarter `CountryRisk` series with NLA Analytics country-risk firm-level CSVs. The main evidence is a set of Pearson correlations at the matched `gvkey`-quarter level and at a quarterly level after first matching `gvkey`-quarter observations.

Only `risk` is compared. Exposure is intentionally not included.

Bottom line: for the 20 reproduced countries currently available, reproduced risk correlates with the paper DTA at 0.90-0.97 across firm-quarters, averaging 0.95. Quarter-level correlations average 0.99.

## Headline Results

These correlations were generated from NLA files in `data/reproduced_v1.0/` against `data/original/FirmCountryQuarter_withexposure.dta`. The table reports the `filled` variant, which applies the same short-gap carry-forward convention used by the original Stata import pipeline. The CSV outputs also include an `observed` variant.

The headline table is rendered from `data/correlations/*.csv`; rerun `countryrisk-correlate` and then `correlation_tables.ipynb` to refresh it after changing inputs.

| Country | Firm-quarter Pearson | Quarter Pearson | Matched firm-quarters | Quarters |
|---|---:|---:|---:|---:|
| `AR` | 0.97 | 0.99 | 315,211 | 72 |
| `AU` | 0.94 | 0.99 | 315,211 | 72 |
| `BE` | 0.95 | 0.99 | 315,211 | 72 |
| `BR` | 0.95 | 0.99 | 315,211 | 72 |
| `CA` | 0.90 | 0.97 | 315,211 | 72 |
| `CL` | 0.93 | 0.99 | 315,211 | 72 |
| `CN` | 0.92 | 0.99 | 315,211 | 72 |
| `CO` | 0.93 | 0.99 | 315,211 | 72 |
| `CZ` | 0.95 | 0.99 | 315,211 | 72 |
| `DE` | 0.95 | 0.99 | 315,211 | 72 |
| `EG` | 0.96 | 0.99 | 315,211 | 72 |
| `FR` | 0.95 | 0.99 | 315,211 | 72 |
| `GB` | 0.94 | 0.99 | 315,211 | 72 |
| `GR` | 0.97 | 1.00 | 315,211 | 72 |
| `HK` | 0.96 | 0.99 | 315,211 | 72 |
| `HU` | 0.97 | 0.99 | 315,211 | 72 |
| `ID` | 0.94 | 0.99 | 315,211 | 72 |
| `IE` | 0.94 | 0.99 | 315,211 | 72 |
| `IN` | 0.93 | 0.98 | 315,211 | 72 |
| `IR` | 0.96 | 0.99 | 315,211 | 72 |
| Average | 0.95 | 0.99 | - | - |

The matched firm-quarter count is the same for every country because each country CSV covers the same call universe. The country-specific score differs, but the available `gvkey`-quarter keys are common across country files.

The `filled` variant is the headline because the benchmark DTA itself reflects the original Stata import/backfill convention. The `observed` variant is included in the output CSVs as a no-fill robustness check.

## Data

Data files are downloaded separately and are not tracked in git.

Obtain the paper-based DTA from the Country Risk project download page: <https://www.country-risk.net/download>. Use the "Firm-country-quarter level" Stata file and place it at `data/original/FirmCountryQuarter_withexposure.dta`.

Obtain the reproduced NLA country-risk series from the NL Analytics curated-measures page: <https://apps.nlanalytics.tech/curated-measures/country-risk>. Place the purchased firm-level CSV files under `data/reproduced_v1.0/`, or pass their directory with `--reproduced-dir`.

Expected local layout:

```text
data/
  original/
    FirmCountryQuarter_withexposure.dta
  reproduced_v1.0/
    NLA_*_countryrisk-*-v10_*_firmlevel.csv
```

Each reproduced NLA CSV must contain `gvkey`, `start_time`, `risk`, and `nr_of_words`. The version tag in the filename is used only to discover country files; the script treats every matching CSV in the reproduced directory as part of the validation set.

## Paper Code Provenance

The public replication package for Hassan et al. (2023) is archived on Zenodo at <https://doi.org/10.5281/zenodo.7783429>. That package does not include the raw score-import script, but it documents the downstream paper build: `data/make.py` treats `raw/refinitiv/scores.dta` as the prepared score input, `data/code/stata/country_quarter.do` and `data/code/stata/firm_country.do` build the paper's analysis panels from it, and `data/code/stata/firmrisk_import.do` uses the same short-gap backfill pattern mirrored here for the reproduced series.

This repository therefore uses the paper-distributed `FirmCountryQuarter_withexposure.dta` as the benchmark panel. It does not attempt to rebuild the paper data from licensed raw transcript inputs.

## What Is Compared

The DTA side is:

```text
CountryRisk
```

`CountryRisk` is already normalized in the DTA and already reflects the original Stata import pipeline's quarterly collapse and backfill.

The reproduced side is computed at the call level as:

```text
100000 * risk / nr_of_words
```

Multiple calls in the same `gvkey`-quarter are collapsed with a simple mean. The output includes two variants:

| Variant | Reproduced value |
|---|---|
| `observed` | matched reproduced gvkey-quarters only |
| `filled` | Stata-style carry-forward for internal firm-quarter gaps up to four quarters |

The quarter-level comparison first restricts to the same matched `gvkey`-quarter observations, then averages those matched observations by quarter before computing Pearson correlations.

This is a validation against the paper-distributed DTA panel. It is not a byte-for-byte rebuild of the original paper code or raw score files.

## Run

Install the package dependencies, then run:

```sh
python3 -m pip install -e .
```

```sh
countryrisk-correlate
```

The command defaults to `data/reproduced_v1.0/`. To use a different reproduced directory:

```sh
countryrisk-correlate --reproduced-dir data/reproduced_v2.2
```

For a quick country subset:

```sh
countryrisk-correlate --countries AR,GB,CA
```

The legacy script path remains available as a thin wrapper:

```sh
python3 scripts/correlate_original_reproduced.py
```

## Tests

The test suite uses synthetic data only, including a tiny generated Stata file and reproduced CSV fixture. It does not require the paper DTA or purchased NLA files.

```sh
python3 -m pip install -e ".[test]"
pytest
```

Continuous integration runs linting, type checks, and tests on Python 3.12, plus the tests on Python 3.10 with pandas 2.0 to cover the declared interpreter and pandas floors.

## Outputs

The script writes outputs to `data/correlations/`:

- `data/correlations/gvkey_quarter_correlations.csv`
- `data/correlations/quarter_correlations.csv`
- `data/correlations/data_manifest.csv`

Use the `pearson` column as the validation statistic. Values close to 1, together with large matched sample sizes, indicate that the NLA series closely tracks the paper-based DTA measure.

The manifest records the DTA and reproduced CSV filenames, file sizes, row counts, and SHA-256 hashes used in the run.

## Notebook

`correlation_tables.ipynb` calls the same package API. Use it if you want to rerun the correlations and inspect the output tables interactively.

The notebook dependencies are optional:

```sh
python3 -m venv venv
venv/bin/python -m pip install -e ".[notebook]"
```

## Limitations

This repository checks correlation and coverage, not byte-for-byte equality. Very high correlations indicate that the reproduced NLA series are close to the paper-based DTA measure over the matched sample, but any skipped country, missing observation, or changed downloaded source file should be checked through the output filenames, sample-size columns, and `data_manifest.csv`.

## License

Code in this repository is licensed under the MIT License. The original and reproduced data files are not included and remain subject to their respective source terms.
