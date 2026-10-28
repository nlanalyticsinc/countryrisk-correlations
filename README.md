# Country Risk Reproduction Correlations

This repository checks whether separately downloaded NLA country-risk CSVs reproduce the paper-based country-risk panel distributed as `FirmCountryQuarter_withexposure.dta`.

The validation compares the DTA's firm-country-quarter `CountryRisk` series with NLA Analytics country-risk firm-level CSVs. The main evidence is a set of Pearson correlations at the matched `gvkey`-quarter level and at a quarterly level after first matching `gvkey`-quarter observations.

Only `risk` is compared. Exposure is intentionally not included.

Bottom line: for the 45 reproduced countries currently available, reproduced risk correlates with the paper DTA at 0.748-0.974 across firm-quarters, averaging 0.933. Quarter-level correlations range from 0.932 to 0.995, averaging 0.983.

## Headline Results

These correlations were generated from the NLA package in `data/nla_country-risk_dataset_2026-06-30/` against `data/original/FirmCountryQuarter_withexposure.dta`. The matched period is 2002Q1-2020Q4. That package predates the October 2026 refresh, and its firm-level files still carried a `gvkey` column. The table has not been rerun on files downloaded since then, which take GVKEY from the crosswalk described under [Data](#data). The table reports the `filled` variant, which applies the same short-gap carry-forward convention used by the original Stata import pipeline. The CSV outputs also include an `observed` variant.

The headline table is rendered from `data/correlations/*.csv`; execute `correlation_tables.ipynb` to rerun the pipeline and refresh the rendered table after changing inputs.

| Country | Firm-quarter Pearson | Quarter Pearson | Matched firm-quarters | Quarters |
|---|---:|---:|---:|---:|
| `AR` | 0.972 | 0.992 | 321,048 | 76 |
| `AU` | 0.944 | 0.986 | 321,048 | 76 |
| `BE` | 0.946 | 0.989 | 321,048 | 76 |
| `BR` | 0.954 | 0.993 | 321,048 | 76 |
| `CA` | 0.898 | 0.967 | 321,048 | 76 |
| `CH` | 0.917 | 0.981 | 321,048 | 76 |
| `CL` | 0.929 | 0.984 | 321,048 | 76 |
| `CN` | 0.917 | 0.990 | 321,048 | 76 |
| `CO` | 0.933 | 0.989 | 321,048 | 76 |
| `CZ` | 0.948 | 0.984 | 321,048 | 76 |
| `DE` | 0.948 | 0.991 | 321,048 | 76 |
| `EG` | 0.955 | 0.992 | 321,048 | 76 |
| `ES` | 0.955 | 0.988 | 321,048 | 76 |
| `FR` | 0.951 | 0.988 | 321,048 | 76 |
| `GB` | 0.944 | 0.993 | 321,048 | 76 |
| `GR` | 0.968 | 0.995 | 321,048 | 76 |
| `HK` | 0.965 | 0.995 | 321,048 | 76 |
| `HU` | 0.974 | 0.987 | 321,048 | 76 |
| `ID` | 0.943 | 0.987 | 321,048 | 76 |
| `IE` | 0.940 | 0.989 | 321,048 | 76 |
| `IL` | 0.748 | 0.932 | 321,048 | 76 |
| `IN` | 0.934 | 0.979 | 321,048 | 76 |
| `IR` | 0.957 | 0.986 | 321,048 | 76 |
| `IT` | 0.966 | 0.990 | 321,048 | 76 |
| `JP` | 0.924 | 0.991 | 321,048 | 76 |
| `KR` | 0.917 | 0.984 | 321,048 | 76 |
| `MX` | 0.867 | 0.936 | 321,048 | 76 |
| `MY` | 0.971 | 0.988 | 321,048 | 76 |
| `NG` | 0.933 | 0.982 | 321,048 | 76 |
| `NL` | 0.929 | 0.989 | 321,048 | 76 |
| `NO` | 0.967 | 0.960 | 321,048 | 76 |
| `NZ` | 0.941 | 0.982 | 321,048 | 76 |
| `PH` | 0.931 | 0.966 | 321,048 | 76 |
| `PK` | 0.967 | 0.983 | 321,048 | 76 |
| `PL` | 0.943 | 0.987 | 321,048 | 76 |
| `RU` | 0.952 | 0.995 | 321,048 | 76 |
| `SA` | 0.938 | 0.989 | 321,048 | 76 |
| `SE` | 0.963 | 0.986 | 321,048 | 76 |
| `SG` | 0.963 | 0.987 | 321,048 | 76 |
| `TH` | 0.908 | 0.987 | 321,048 | 76 |
| `TR` | 0.963 | 0.991 | 321,048 | 76 |
| `TW` | 0.786 | 0.965 | 321,048 | 76 |
| `US` | 0.857 | 0.973 | 321,048 | 76 |
| `VE` | 0.968 | 0.988 | 321,048 | 76 |
| `ZA` | 0.883 | 0.973 | 321,048 | 76 |
| Average | 0.933 | 0.983 | - | - |

The matched firm-quarter count is the same for every country because each country CSV covers the same call universe. The country-specific score differs, but the available `gvkey`-quarter keys are common across country files.

The `filled` variant is the headline because the benchmark DTA itself reflects the original Stata import/backfill convention. The `observed` variant is included in the output CSVs as a no-fill robustness check.

The lowest filled correlations in this run are `IL` and `TW` at the firm-quarter level and `IL` at the quarter level. The CSV outputs contain full-precision values for all countries and both variants.

## Data

Data files are downloaded separately and are not tracked in git.

Obtain the paper-based DTA from the Country Risk project download page: <https://www.country-risk.net/download>. Use the "Firm-country-quarter level" Stata file and place it at `data/original/FirmCountryQuarter_withexposure.dta`.

Obtain the reproduced NLA country-risk series from the NL Analytics curated-measures page: <https://apps.nlanalytics.tech/curated-measures/country-risk>. Its "Download dataset (ZIP)" button downloads `nla_country-risk_dataset_YYYY-MM-DD.zip`. Unzip it into `data/nla_country-risk_dataset_YYYY-MM-DD/`. By default, the pipeline selects the most recent directory matching that name. If no packaged dataset exists, it falls back to `data/reproduced_v1.0/`. The legacy flat-file export also remains explicitly selectable through `--reproduced-dir`.

Supported local layouts:

```text
data/
  original/
    FirmCountryQuarter_withexposure.dta
  nla_country-risk_dataset_YYYY-MM-DD/
    README.txt
    gvkeys.csv.gz
    series/
      01-countryrisk-argentina-v11-70ca2a2b/
        firmlevel.csv.gz
        timeseries.csv.gz

# Legacy flat export: files from each series page
data/
  reproduced_v1.0/
    NLA_*_countryrisk-*-v10_*_firmlevel.csv
    NLA_*_gvkeys.csv
```

The package root, its `series/` directory, or an individual series directory can be passed to `--reproduced-dir`. Only the firm-level files and the GVKEY crosswalk are used; the aggregate `timeseries.csv.gz` has no firm-level observations.

Gzip files are read directly and do not need to be unpacked. The pipeline detects gzip from a file's first bytes, not its name: a file downloaded from a series page can hold gzip bytes under a plain `.csv` name.

### GVKEY crosswalk

Firm-level files downloaded since the October 2026 refresh have no `gvkey` column. GVKEY ships in the measure's crosswalk, `gvkeys.csv`, with the columns `earningscallID`, `gvkey_compustat`, `sic_compustat`, and `sic_compustat_description`. Every series of the measure shares the same crosswalk:

- A ZIP packaged since 22 October 2026 includes it once, as `gvkeys.csv.gz` at its root, next to `series/`. The ZIP's `README.txt` gives the packaging date. An older ZIP has no crosswalk; if its firm-level files lack `gvkey`, take the crosswalk from a series page.
- On a series page it is the "Crosswalk to GVKey (includes SIC)" download, saved as `NLA_*_gvkeys.csv`. Download it from one series page and put it next to the firm-level files.

For a firm-level file without `gvkey`, the pipeline joins `gvkey_compustat` on `earningscallID`. Calls without a GVKEY in the crosswalk drop out, as calls with a blank `gvkey` always have; the log reports how many. Files that carry `gvkey`, such as the June 2026 package behind the table above, are read as before and ignore the crosswalk. To use a crosswalk stored elsewhere, pass `--gvkeys-file`.

Call IDs are trimmed, and blank IDs are ignored. Crosswalk overlap is checked using call IDs, including calls whose GVKEY is missing; a file with nonblank call IDs that are all absent from the crosswalk fails. A country with no usable GVKEYs is skipped, allowing other countries to run.

GVKEYs accept digits with an optional all-zero decimal part (`001004`, `1004`, `1004.0`), within the signed 64-bit range. Blank values and the case-insensitive markers `.`, `NA`, `N/A`, `NaN`, `NULL`, `None`, and `<NA>` mean missing. Malformed nonmissing GVKEYs fail with the source file and row number. These rules apply to the crosswalk and both original and reproduced inputs.

Each reproduced NLA firm-level CSV must contain `start_time`, `risk`, `nr_of_words`, and either `gvkey` or `earningscallID`. The version tag and series identifier are recorded as provenance but do not select different scoring logic. Discovery fails rather than mixing two files for the same country.

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

Create a virtual environment, install the package dependencies, then run:

```sh
python3 -m venv venv
venv/bin/python -m pip install -e .
```

```sh
venv/bin/countryrisk-correlate
```

The command defaults to the packaged dataset with the most recent valid `YYYY-MM-DD` suffix. To use the legacy flat-file layout explicitly:

```sh
venv/bin/countryrisk-correlate --reproduced-dir data/reproduced_v1.0
```

To use another packaged dataset, pass its package root without decompressing it:

```sh
venv/bin/countryrisk-correlate --reproduced-dir data/nla_country-risk_dataset_YYYY-MM-DD
```

To use a GVKEY crosswalk that is not next to the firm-level files:

```sh
venv/bin/countryrisk-correlate --gvkeys-file path/to/gvkeys.csv.gz
```

For a quick country subset:

```sh
venv/bin/countryrisk-correlate --countries AR,GB,CA
```

The legacy script path remains available as a thin wrapper:

```sh
venv/bin/python scripts/correlate_original_reproduced.py
```

## Tests

The test suite uses synthetic data only, including a tiny generated Stata file and reproduced CSV fixture. It does not require the paper DTA or purchased NLA files.

```sh
python3 -m venv venv
venv/bin/python -m pip install -e ".[test]"
venv/bin/pytest
```

Continuous integration runs linting, type checks, and tests on Python 3.12, plus the tests on Python 3.10 with pandas 2.0 to cover the declared interpreter and pandas floors.

## Outputs

The script writes outputs to `data/correlations/`:

- `data/correlations/gvkey_quarter_correlations.csv`
- `data/correlations/quarter_correlations.csv`
- `data/correlations/data_manifest.csv`

Use the `pearson` column as the validation statistic. Values close to 1, together with large matched sample sizes, indicate that the NLA series closely tracks the paper-based DTA measure.

The manifest records the DTA and reproduced CSV paths, source layouts, dataset dates, series versions and identifiers, compression, file sizes, row counts, and SHA-256 hashes used in the run. When a crosswalk supplies GVKEY, it is listed too, with the role `gvkey_crosswalk`.

## Notebook

`correlation_tables.ipynb` calls the same package API, writes the correlation CSVs, and renders the headline table. Use it to rerun the correlations and inspect the output tables interactively.

The notebook dependencies are optional:

```sh
python3 -m venv venv
venv/bin/python -m pip install -e ".[notebook]"
```

Execute the notebook in place to generate the CSV outputs and refresh its rendered tables:

```sh
venv/bin/jupyter nbconvert --to notebook --execute --inplace correlation_tables.ipynb
```

## Limitations

This repository checks correlation and coverage, not byte-for-byte equality. Very high correlations indicate that the reproduced NLA series are close to the paper-based DTA measure over the matched sample, but any skipped country, missing observation, or changed downloaded source file should be checked through the output filenames, sample-size columns, and `data_manifest.csv`.

## License

Code in this repository is licensed under the MIT License. The original and reproduced data files are not included and remain subject to their respective source terms.
