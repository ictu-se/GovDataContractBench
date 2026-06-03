# GovDataContractBench

GovDataContractBench is a reproducible benchmark for studying multi-layer
contract-drift detection on public data-sharing artifacts. The benchmark uses
public OpenAPI specifications, open-government CKAN metadata, official FHIR US
Core examples, and a small SMART-on-FHIR/Synthea bulk sample.

The repository contains code, public-data snapshots, generated benchmark cases,
and result tables. It does not contain the manuscript.

## What Is Included

- `scripts/fetch_public_datasets.py`: fetches the public artifact snapshots.
- `scripts/summarize_datasets.py`: summarizes the downloaded datasets.
- `scripts/gov_contract_bench.py`: generates controlled mutation cases and
  evaluates detector configurations.
- `scripts/fetch_openapi_histories.py`: fetches natural OpenAPI version pairs.
- `scripts/analyze_natural_drift.py`: analyzes natural OpenAPI drift alerts.
- `scripts/heuristic_label_audit.py`: creates transparent heuristic pre-labels
  for the natural-drift manual audit packet.
- `data/`: current public-data snapshot used for the included results.
- `results/`: generated summary tables, benchmark metrics, mutation cases, and
  natural-drift audit files.

## Requirements

- Python 3.10 or newer.
- No third-party Python packages are required for the current scripts.
- Internet access is required only when refreshing datasets or natural version
  pairs.

Create an optional virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Reproduce The Included Results

Run from the repository root:

```bash
python3 scripts/summarize_datasets.py

python3 scripts/gov_contract_bench.py \
  --openapi-artifacts 150 \
  --ckan-artifacts 1000 \
  --fhir-artifacts 2000 \
  --max-mutations-per-artifact 5

python3 scripts/analyze_natural_drift.py --audit-sample 120
python3 scripts/heuristic_label_audit.py
```

This reproduces the result files under:

- `results/dataset_summary.*`
- `results/benchmark/*`
- `results/natural_drift/*`

## Refresh The Public Data Snapshot

To refetch all public datasets and regenerate all results:

```bash
python3 scripts/fetch_public_datasets.py \
  --apis-guru-limit 150 \
  --data-gov-limit 10000

python3 scripts/summarize_datasets.py

python3 scripts/gov_contract_bench.py \
  --openapi-artifacts 150 \
  --ckan-artifacts 1000 \
  --fhir-artifacts 2000 \
  --max-mutations-per-artifact 5

python3 scripts/fetch_openapi_histories.py \
  --method apis-guru \
  --max-files 40 \
  --max-pairs 60 \
  --max-pairs-per-api 3

python3 scripts/analyze_natural_drift.py --audit-sample 120
python3 scripts/heuristic_label_audit.py
```

To refresh only CKAN metadata:

```bash
python3 scripts/fetch_public_datasets.py \
  --skip-apis-guru \
  --skip-fhir \
  --skip-smart-bulk-fhir \
  --data-gov-limit 10000

python3 scripts/summarize_datasets.py
```

## Current Snapshot

The current snapshot contains:

| Source | Size |
|---|---:|
| APIs.guru OpenAPI Directory | 150 specifications |
| Open-government CKAN metadata | 10,000 package records |
| FHIR US Core examples | 141 resources |
| SMART-on-FHIR/Synthea small sample | 7,887 resources |
| APIs.guru natural OpenAPI version pairs | 60 pairs |

The current controlled benchmark contains 14,561 mutation cases:

| Label | Cases |
|---|---:|
| `breaking_schema` | 4,430 |
| `breaking_provenance` | 4,000 |
| `breaking_semantic` | 3,012 |
| `breaking_security` | 116 |
| `non_breaking` | 3,003 |

The current detector metrics are:

| Detector | Precision | Recall | F1 | Severity-weighted recall |
|---|---:|---:|---:|---:|
| `parser_only` | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `structural_required` | 1.0000 | 0.6602 | 0.7954 | 0.6293 |
| `structural_plus_semantic` | 1.0000 | 0.8993 | 0.9470 | 0.9232 |
| `compatibility` | 1.0000 | 0.7547 | 0.8602 | 0.6997 |
| `proposed_multilayer` | 1.0000 | 0.9938 | 0.9969 | 0.9936 |

## Data-Source Notes

The CKAN collection script attempts the Data.gov CKAN endpoint first. In the
current local collection environment, that endpoint was unavailable, so the
script used the public data.gov.au CKAN endpoint as a fallback. The benchmark
therefore reports this source as open-government CKAN metadata.

FHIR US Core examples are official public examples. The SMART-on-FHIR sample is
Synthea-generated data from the public SMART Health IT sample bulk FHIR dataset.
The natural OpenAPI drift sample uses adjacent public API versions from
APIs.guru.

## Repository Policy

This repository is intended for benchmark code and reproducibility artifacts.
Manuscripts, journal templates, local notes, and generated paper PDFs are
excluded from version control.

## License

Code in this repository is released under the MIT License. Public datasets retain
their original upstream licenses and terms.
