# KPI Ontology

RDF/OWL ontology for describing Key Performance Indicators (KPIs) that are computed through aggregation operations over instance data from a reference ontology.

The model captures the essential parts of a KPI definition:

- the reference ontology and source data
- the property being aggregated
- the aggregation operator, such as `SUM`, `COUNT`, or `AVG`
- optional granularity dimensions used to group results
- computed aggregation results and their dimension values

The ontology is domain-neutral and can be used anywhere aggregated metrics are represented as RDF.

## Namespace

The ontology uses the following base namespace:

```text
https://semantic.adorsys.com/meta/kpi/
```

## Repository Contents

- `kpi_ontology.ttl` - main OWL ontology for KPI descriptions, dimensions, values, and results.
- `kpi_vocabulary.ttl` - SKOS vocabulary for supported aggregation operators.
- `kpi_ontology_merged.ttl` - merged ontology and aggregation operator vocabulary.
- `kpi_results.ttl` - example KPI result data using the ontology.

## Status

The ontology metadata marks version `1.0` as draft.

## Usage

Use `kpi_ontology.ttl` together with `kpi_vocabulary.ttl` when loading the ontology and controlled vocabulary separately. Use `kpi_ontology_merged.ttl` when a single combined Turtle file is more convenient.

Example resources in `kpi_results.ttl` demonstrate an average current gross payment KPI grouped by gender and education level.

## License

This repository is licensed under the MIT License. See [LICENSE](LICENSE).
