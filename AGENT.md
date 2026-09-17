# Development Practices

This repository follows Cookiecutter Data Science conventions with a `src/`
layout. Keep raw data immutable and keep finalized logic out of notebooks.

## Commands

- `just install`: install the project and development dependencies with `uv`.
- `just test`: run pytest.
- `just lint`: run Ruff checks and formatting validation.
- `just init-db`: create the empty DuckDB schema.
- `just run`: execute the ingestion pipeline.

Use `uv add <package>` or `uv add --dev <package>` for dependencies. Commit
`uv.lock` after dependency changes.

## Structure

- `data/raw/`: immutable provider downloads; never modify in place.
- `data/interim/`: intermediate extracts and cached transformations.
- `data/processed/`: generated DuckDB databases and analysis-ready outputs.
- `src/desfibrilator/`: installable package and pipeline code.
- `notebooks/`: exploration only, never pipeline steps.
- `models/`: model artefacts with a colocated `config.yaml`.
- `reports/figures/`: generated publication figures.
- `tests/`: tests for all core logic.

## Engineering rules

- Use paths from configuration, not hardcoded machine-specific paths.
- Document public functions and classes with docstrings.
- Make transformations deterministic and record source provenance.
- Do not commit source datasets, generated databases, secrets, or personally
  identifiable information.
- Keep `main` reproducible and use feature or fix branches for changes.
