# Hookless 500-document corpus workflow

This workflow creates a reproducible, domain-based corpus for the hookless bicycle rim study while preserving an auditable record of discovery, screening, exclusion, extraction, deduplication, quota selection, and sentence segmentation.

## Design

The default configuration targets 500 English-language documents across five discourse communities:

- Manufacturer: 100
- Media: 150
- Forum: 125
- Technical / Engineering: 75
- Standards: 50

The strategy is purposive and domain-based. It is intended to compare institutional discourse communities, not estimate the prevalence of hookless discourse across the entire internet.

## Installation on macOS

Open Terminal in the CDAT Professional repository and run:

```bash
cd /path/to/CDAT-Professional
git fetch origin
git switch feature/hookless-corpus-builder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run the corpus builder

```bash
python -m cdat.corpus_builder corpus_projects/hookless_500.yaml
```

The process may encounter inaccessible pages, anti-bot restrictions, deleted pages, and search-provider rate limits. These are recorded as exclusions rather than silently discarded.

## Outputs

Outputs are written to `outputs/hookless_500/`:

- `document_screening.csv`: every discovered URL and its screening outcome
- `cdat_source_manifest.csv`: included sources formatted for CDAT import
- `sentence_corpus.csv`: sentence-level corpus with adjacent context
- `run_summary.json`: collection totals by discourse community
- `documents/`: extracted plain-text documents

## Import into CDAT Professional

1. Launch CDAT Professional.
2. Create or open the hookless project.
3. Open the Sources page.
4. Select CSV import.
5. Import `outputs/hookless_500/cdat_source_manifest.csv`.
6. Review the pending records and confirm inclusion decisions.

## Reproducibility record

Before analysis, archive the following together:

- the exact YAML configuration
- the complete `document_screening.csv`
- the extracted document directory
- the sentence corpus
- the Git commit SHA
- the date, timezone, operating system, and Python version

Do not manually delete failed or excluded records from the screening CSV. Their retention is necessary for the corpus flow diagram and exclusion accounting.

## Methodological cautions

Sentence-level observations are clustered within documents. Use sentence-level contingency tables descriptively, but conduct at least one document-level or cluster-adjusted robustness analysis. The final manuscript should not claim that the corpus represents all online hookless discourse. It represents the selected domains, queries, timeframe, inclusion rules, and discourse-community quotas.
