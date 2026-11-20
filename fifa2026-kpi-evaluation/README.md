# FIFA World Cup 2026 KPI Experiment

This folder contains the reproducible FIFA World Cup 2026 evaluation used in
the ESWC 2027 paper. The experiment is self-contained: the required reference
ontology and instance data are packaged in `fifa2026-kpi-evaluation/input/`.

## Inputs

- `input/fifa_world_cup_2026.ttl` - reference ontology
- `input/fifa-world-cup-2026_instances.ttl` - RDF instance data
- `../kpi_ontology_merged.ttl` - KPIOnt ontology, operator vocabulary, and SHACL shapes

The packaged FIFA ontology and instance file use the same football ontology
namespace. The script reports role-model classes/properties that are present in
the instance data but absent from the packaged ontology.

## Run

From the repository root:

```bash
python3 -m venv fifa2026-kpi-evaluation/.venv
fifa2026-kpi-evaluation/.venv/bin/python -m pip install -r fifa2026-kpi-evaluation/requirements.txt
fifa2026-kpi-evaluation/.venv/bin/python fifa2026-kpi-evaluation/fifa2026_kpi_evaluation.py
```

The script can also be run from another working directory because its default
paths are resolved relative to this file.

## Outputs

Outputs are written to `fifa2026-kpi-evaluation/output/`:

- `fifa2026_kpi_evaluation.md` - compact human-readable report
- `fifa2026_kpi_evaluation.json` - machine-readable results
- `fifa2026_kpi_instances.ttl` - generated KPIOnt result instances
- one CSV file per KPI query

The generated KPI Turtle is validated against the KPIOnt SHACL shapes. A
successful run ends with `SHACL conforms: True`.

## Custom Paths

Use these options to override the packaged defaults:

```bash
fifa2026-kpi-evaluation/.venv/bin/python fifa2026-kpi-evaluation/fifa2026_kpi_evaluation.py \
  --ontology fifa2026-kpi-evaluation/input/fifa_world_cup_2026.ttl \
  --instances fifa2026-kpi-evaluation/input/fifa-world-cup-2026_instances.ttl \
  --kpi-shapes kpi_ontology_merged.ttl \
  --out-dir fifa2026-kpi-evaluation/output
```
