#!/usr/bin/env python3
"""Run a reproducible KPI experiment on the FIFA World Cup 2026 RDF data.

The script uses the packaged Turtle files in fifa2026-kpi-evaluation/input,
checks whether the instance data and ontology align, executes KPI-style SPARQL
aggregations in an in-memory RDFLib graph, and materializes the results as
KPIOnt instances.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

try:
    from pyshacl import validate as shacl_validate
except Exception:  # pragma: no cover - optional dependency at runtime
    shacl_validate = None


EXPERIMENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EXPERIMENT_DIR.parent
INPUT_DIR = EXPERIMENT_DIR / "input"
OUTPUT_DIR = EXPERIMENT_DIR / "output"

ONTOLOGY_FILE = INPUT_DIR / "fifa_world_cup_2026.ttl"
INSTANCES_FILE = INPUT_DIR / "fifa-world-cup-2026_instances.ttl"

DATA_ONTOLOGY_NS = "https://data.adorsys.com/ontology/sport/football/"
DEFAULT_KPI_SHAPES = PROJECT_DIR / "kpi_ontology_merged.ttl"

KPI = Namespace("https://semantic.adorsys.com/meta/kpi/")
INST = Namespace("https://semantic.adorsys.com/resource/kpi/instance/fifa2026/")

STANDARD_NAMESPACES = (
    str(RDF),
    str(RDFS),
    str(OWL),
    str(XSD),
    "http://www.w3.org/2004/02/skos/core#",
    "http://purl.org/dc/terms/",
)

COMPATIBLE_DATATYPES = {
    str(XSD.string): {None, str(XSD.string), str(RDF.langString)},
    str(XSD.anyURI): {str(XSD.anyURI), str(XSD.string), None},
    str(XSD.integer): {
        str(XSD.integer),
        str(XSD.int),
        str(XSD.long),
        str(XSD.nonNegativeInteger),
        str(XSD.positiveInteger),
        str(XSD.decimal),
    },
    str(XSD.decimal): {
        str(XSD.decimal),
        str(XSD.integer),
        str(XSD.int),
        str(XSD.long),
        str(XSD.float),
        str(XSD.double),
    },
    str(XSD.float): {str(XSD.float), str(XSD.decimal), str(XSD.double)},
    str(XSD.double): {str(XSD.double), str(XSD.float), str(XSD.decimal)},
    str(XSD.date): {str(XSD.date), str(XSD.dateTime)},
    str(XSD.dateTime): {str(XSD.dateTime), str(XSD.date)},
    str(XSD.boolean): {str(XSD.boolean)},
}


@dataclass(frozen=True)
class KpiSpec:
    key: str
    label: str
    operator: str
    aggregation_property: str
    dimensions: Tuple[str, ...]
    query: str


KPI_SPECS: Tuple[KpiSpec, ...] = (
    KpiSpec(
        key="goals_by_group",
        label="Total goals scored by group",
        operator="Sum",
        aggregation_property="goalsFor",
        dimensions=("groupName",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?groupName (SUM(?goalsFor) AS ?value)
WHERE {
  ?standing a football:Standings ;
    football:goalsFor ?goalsFor ;
    football:standingsInGroup ?group .
  ?group football:groupName ?groupName .
}
GROUP BY ?groupName
ORDER BY ?groupName
""",
    ),
    KpiSpec(
        key="matches_by_stage",
        label="Number of matches by tournament stage",
        operator="Count",
        aggregation_property="stage",
        dimensions=("stage",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?stage (COUNT(?stage) AS ?value)
WHERE {
  ?match a football:Match ;
    football:stage ?stage .
}
GROUP BY ?stage
ORDER BY ?stage
""",
    ),
    KpiSpec(
        key="attendance_by_stage",
        label="Average attendance by tournament stage",
        operator="Average",
        aggregation_property="attendance",
        dimensions=("stage",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?stage (AVG(?attendance) AS ?value)
WHERE {
  ?match a football:Match ;
    football:attendance ?attendance ;
    football:stage ?stage .
}
GROUP BY ?stage
ORDER BY ?stage
""",
    ),
    KpiSpec(
        key="matches_by_venue",
        label="Number of matches by venue",
        operator="Count",
        aggregation_property="playedAtVenue",
        dimensions=("venueName",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?venueName (COUNT(?venue) AS ?value)
WHERE {
  ?match a football:Match ;
    football:playedAtVenue ?venue .
  ?venue football:venueName ?venueName .
}
GROUP BY ?venueName
ORDER BY DESC(?value) ?venueName
""",
    ),
    KpiSpec(
        key="shots_by_team",
        label="Average shots per match-team record by team",
        operator="Average",
        aggregation_property="shotsTotal",
        dimensions=("teamName",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?teamName (AVG(?shotsTotal) AS ?value)
WHERE {
  ?stats a football:MatchTeamStatistics ;
    football:shotsTotal ?shotsTotal ;
    football:statisticsForTeam ?team .
  ?team football:teamName ?teamName .
}
GROUP BY ?teamName
ORDER BY DESC(?value) ?teamName
""",
    ),
    KpiSpec(
        key="home_win_odds_by_stage",
        label="Average home-win odds by tournament stage",
        operator="Average",
        aggregation_property="oddsHomeWin",
        dimensions=("stage",),
        query="""
PREFIX football: <https://data.adorsys.com/ontology/sport/football/>
SELECT ?stage (AVG(?oddsHomeWin) AS ?value)
WHERE {
  ?match a football:Match ;
    football:oddsHomeWin ?oddsHomeWin ;
    football:stage ?stage .
}
GROUP BY ?stage
ORDER BY ?stage
""",
    ),
)


def local_name(term: URIRef) -> str:
    value = str(term)
    if "#" in value:
        return value.rsplit("#", 1)[1]
    return value.rstrip("/").rsplit("/", 1)[1]


def namespace_of(term: URIRef) -> str:
    value = str(term)
    if "#" in value:
        return value.rsplit("#", 1)[0] + "#"
    return value.rsplit("/", 1)[0] + "/"


def parse_graph(path: Path) -> Tuple[Graph, float]:
    graph = Graph()
    start = time.perf_counter()
    graph.parse(path, format="turtle")
    elapsed = time.perf_counter() - start
    return graph, elapsed


def term_set(graph: Graph, rdf_type: URIRef) -> Set[URIRef]:
    return {s for s in graph.subjects(RDF.type, rdf_type) if isinstance(s, URIRef)}


def used_terms(instances: Graph) -> Tuple[Set[URIRef], Set[URIRef]]:
    used_classes = {
        o
        for o in instances.objects(None, RDF.type)
        if isinstance(o, URIRef) and not str(o).startswith(STANDARD_NAMESPACES)
    }
    used_properties = {
        p
        for p in instances.predicates()
        if isinstance(p, URIRef) and not str(p).startswith(STANDARD_NAMESPACES)
    }
    return used_classes, used_properties


def by_local(terms: Iterable[URIRef]) -> Dict[str, URIRef]:
    result: Dict[str, URIRef] = {}
    for term in terms:
        result.setdefault(local_name(term), term)
    return result


def subclass_closure(ontology: Graph) -> Dict[str, Set[str]]:
    direct: Dict[str, Set[str]] = defaultdict(set)
    for child, _, parent in ontology.triples((None, RDFS.subClassOf, None)):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            direct[local_name(child)].add(local_name(parent))

    closure: Dict[str, Set[str]] = {}
    classes = {local_name(t) for t in term_set(ontology, OWL.Class)}
    for cls in classes:
        seen = {cls}
        queue = deque([cls])
        while queue:
            current = queue.popleft()
            for parent in direct.get(current, set()):
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        closure[cls] = seen
    return closure


def uri_map_for_property(
    ontology: Graph, property_terms: Set[URIRef]
) -> Dict[str, Dict[str, Set[str]]]:
    result: Dict[str, Dict[str, Set[str]]] = {}
    for prop in property_terms:
        name = local_name(prop)
        domains = {local_name(o) for o in ontology.objects(prop, RDFS.domain) if isinstance(o, URIRef)}
        ranges = {str(o) for o in ontology.objects(prop, RDFS.range) if isinstance(o, URIRef)}
        result[name] = {"domains": domains, "ranges": ranges}
    return result


def literal_datatype_ok(literal: Literal, range_uri: str) -> bool:
    datatype = str(literal.datatype) if literal.datatype else None
    if range_uri not in COMPATIBLE_DATATYPES:
        return True
    return datatype in COMPATIBLE_DATATYPES[range_uri]


def class_matches(actual_types: Set[str], allowed: Set[str], closure: Dict[str, Set[str]]) -> bool:
    if not allowed:
        return True
    for actual in actual_types:
        actual_and_parents = closure.get(actual, {actual})
        if actual_and_parents & allowed:
            return True
    return False


def check_alignment(ontology: Graph, instances: Graph) -> Dict[str, object]:
    ont_classes = term_set(ontology, OWL.Class)
    ont_obj_props = term_set(ontology, OWL.ObjectProperty)
    ont_data_props = term_set(ontology, OWL.DatatypeProperty)
    ont_props = ont_obj_props | ont_data_props

    used_classes, used_props = used_terms(instances)
    used_class_names = set(by_local(used_classes))
    used_prop_names = set(by_local(used_props))
    ont_class_names = set(by_local(ont_classes))
    ont_prop_names = set(by_local(ont_props))

    exact_class_matches = len(used_classes & ont_classes)
    exact_prop_matches = len(used_props & ont_props)

    alignment = {
        "ontology_classes": len(ont_classes),
        "ontology_properties": len(ont_props),
        "ontology_object_properties": len(ont_obj_props),
        "ontology_datatype_properties": len(ont_data_props),
        "used_classes": len(used_classes),
        "used_properties": len(used_props),
        "exact_class_matches": exact_class_matches,
        "exact_property_matches": exact_prop_matches,
        "local_class_matches": len(used_class_names & ont_class_names),
        "local_property_matches": len(used_prop_names & ont_prop_names),
        "classes_missing_from_ontology_by_local_name": sorted(used_class_names - ont_class_names),
        "properties_missing_from_ontology_by_local_name": sorted(used_prop_names - ont_prop_names),
        "classes_unused_in_data_by_local_name": sorted(ont_class_names - used_class_names),
        "properties_unused_in_data_by_local_name": sorted(ont_prop_names - used_prop_names),
    }
    return alignment


def check_schema_conformance(ontology: Graph, instances: Graph) -> Dict[str, object]:
    all_props = term_set(ontology, OWL.ObjectProperty) | term_set(ontology, OWL.DatatypeProperty)
    functional_props = {local_name(s) for s in ontology.subjects(RDF.type, OWL.FunctionalProperty)}
    property_schema = uri_map_for_property(ontology, all_props)
    closure = subclass_closure(ontology)
    type_by_subject: Dict[URIRef, Set[str]] = defaultdict(set)
    for subject, obj in instances.subject_objects(RDF.type):
        if isinstance(subject, URIRef) and isinstance(obj, URIRef):
            type_by_subject[subject].add(local_name(obj))

    domain_violations: List[Dict[str, str]] = []
    range_violations: List[Dict[str, str]] = []
    domain_violation_total = 0
    range_violation_total = 0
    functional_values: Dict[Tuple[URIRef, str], Set[object]] = defaultdict(set)
    checked_domain = 0
    checked_range = 0

    for subject, predicate, obj in instances:
        if not isinstance(predicate, URIRef) or not str(predicate).startswith(DATA_ONTOLOGY_NS):
            continue
        prop = local_name(predicate)
        schema = property_schema.get(prop)
        if not schema:
            continue

        if prop in functional_props:
            functional_values[(subject, prop)].add(obj)

        domains = schema["domains"]
        if domains:
            checked_domain += 1
            actual_types = type_by_subject.get(subject, set())
            if not actual_types or not class_matches(actual_types, domains, closure):
                domain_violation_total += 1
                if len(domain_violations) < 25:
                    domain_violations.append(
                        {
                            "subject": str(subject),
                            "property": prop,
                            "expected": ", ".join(sorted(domains)),
                            "actual_types": ", ".join(sorted(actual_types)) or "(none)",
                        }
                    )

        ranges = schema["ranges"]
        if ranges:
            checked_range += 1
            object_ok = False
            for expected in ranges:
                if expected.startswith(str(XSD)):
                    if isinstance(obj, Literal) and literal_datatype_ok(obj, expected):
                        object_ok = True
                        break
                elif isinstance(obj, URIRef):
                    expected_local = local_name(URIRef(expected))
                    actual_types = type_by_subject.get(obj, set())
                    if class_matches(actual_types, {expected_local}, closure):
                        object_ok = True
                        break
                elif isinstance(obj, Literal) and expected == str(XSD.string):
                    object_ok = True
                    break
            if not object_ok and len(range_violations) < 25:
                range_violation_total += 1
                if isinstance(obj, Literal):
                    actual = str(obj.datatype) if obj.datatype else "plain literal"
                else:
                    actual = ", ".join(sorted(type_by_subject.get(obj, set()))) or "(none)"
                range_violations.append(
                    {
                        "subject": str(subject),
                        "property": prop,
                        "expected": ", ".join(sorted(ranges)),
                        "actual": actual,
                        "object": str(obj),
                    }
                )

            elif not object_ok:
                range_violation_total += 1

    functional_violations = [
        {
            "subject": str(subject),
            "property": prop,
            "value_count": len(values),
        }
        for (subject, prop), values in functional_values.items()
        if len(values) > 1
    ]

    return {
        "checked_domain_triples": checked_domain,
        "checked_range_triples": checked_range,
        "domain_violation_count": domain_violation_total,
        "range_violation_count": range_violation_total,
        "domain_violation_samples": domain_violations,
        "range_violation_samples": range_violations,
        "functional_property_violations": len(functional_violations),
        "functional_property_violation_samples": functional_violations[:25],
    }


def dataset_summary(instances: Graph) -> Dict[str, object]:
    football = Namespace(DATA_ONTOLOGY_NS)
    counts_query = f"""
PREFIX football: <{DATA_ONTOLOGY_NS}>
SELECT ?class (COUNT(?s) AS ?count)
WHERE {{ ?s a ?class . FILTER(STRSTARTS(STR(?class), "{DATA_ONTOLOGY_NS}")) }}
GROUP BY ?class
ORDER BY DESC(?count) ?class
"""
    class_counts = [
        {"class": local_name(row["class"]), "count": int(row["count"])}
        for row in instances.query(counts_query)
    ]
    return {
        "triples": len(instances),
        "classes_with_instances": len(class_counts),
        "top_class_counts": class_counts[:15],
        "matches": int(
            next(
                iter(
                    instances.query(
                        f"PREFIX football: <{football}> SELECT (COUNT(?s) AS ?c) WHERE {{ ?s a football:Match . }}"
                    )
                )
            )["c"]
        ),
        "teams": int(
            next(
                iter(
                    instances.query(
                        f"PREFIX football: <{football}> SELECT (COUNT(?s) AS ?c) WHERE {{ ?s a football:Team . }}"
                    )
                )
            )["c"]
        ),
        "venues": int(
            next(
                iter(
                    instances.query(
                        f"PREFIX football: <{football}> SELECT (COUNT(?s) AS ?c) WHERE {{ ?s a football:Venue . }}"
                    )
                )
            )["c"]
        ),
    }


def run_kpi_queries(instances: Graph) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for spec in KPI_SPECS:
        start = time.perf_counter()
        rows = list(instances.query(spec.query))
        elapsed = time.perf_counter() - start
        result_rows = []
        for row in rows:
            as_dict = {}
            for name in row.labels:
                value = row[name]
                if isinstance(value, Literal):
                    parsed = value.toPython()
                    if isinstance(parsed, Decimal):
                        parsed = float(parsed)
                    as_dict[name] = parsed
                else:
                    as_dict[name] = str(value)
            result_rows.append(as_dict)
        results.append(
            {
                "key": spec.key,
                "label": spec.label,
                "operator": spec.operator,
                "aggregation_property": spec.aggregation_property,
                "dimensions": list(spec.dimensions),
                "row_count": len(result_rows),
                "elapsed_ms": round(elapsed * 1000, 2),
                "sample_rows": result_rows[:10],
                "all_rows": result_rows,
            }
        )
    return results


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def decimal_literal(value: object) -> Literal:
    def normalize_lexical(text: str) -> str:
        if "E" in text or "e" in text:
            text = format(Decimal(text), "f")
        if "." not in text:
            text += ".0"
        return text

    if isinstance(value, Decimal):
        return Literal(normalize_lexical(format(value, "f")), datatype=XSD.decimal)
    if isinstance(value, int):
        return Literal(f"{value}.0", datatype=XSD.decimal)
    if isinstance(value, float):
        if math.isfinite(value):
            return Literal(normalize_lexical(f"{value:.6f}".rstrip("0").rstrip(".")), datatype=XSD.decimal)
        return Literal("0.0", datatype=XSD.decimal)
    return Literal(normalize_lexical(str(value)), datatype=XSD.decimal)


def stable_input_uri(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(PROJECT_DIR.resolve())
        return f"file:{relative.as_posix()}"
    except ValueError:
        return path.resolve().as_uri()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_DIR.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def materialize_kpis(query_results: Sequence[Dict[str, object]], dataset_uri: str) -> Graph:
    graph = Graph()
    graph.bind("kpi", KPI)
    graph.bind("inst", INST)
    graph.bind("xsd", XSD)

    for result in query_results:
        spec = next(spec for spec in KPI_SPECS if spec.key == result["key"])
        kpi_uri = INST[f"kpi-{spec.key}"]
        graph.add((kpi_uri, RDF.type, KPI.KeyPerformanceIndicator))
        graph.add((kpi_uri, KPI.kpiLabel, Literal(spec.label)))
        graph.add((kpi_uri, KPI.referenceOntologyURI, Literal(DATA_ONTOLOGY_NS, datatype=XSD.anyURI)))
        graph.add((kpi_uri, KPI.dataSourceURI, Literal(dataset_uri, datatype=XSD.anyURI)))
        graph.add(
            (
                kpi_uri,
                KPI.aggregationPropertyURI,
                Literal(DATA_ONTOLOGY_NS + spec.aggregation_property, datatype=XSD.anyURI),
            )
        )
        graph.add((kpi_uri, KPI.hasAggregationOperator, KPI[spec.operator]))

        dim_uris = {}
        for dim in spec.dimensions:
            dim_uri = INST[f"dim-{spec.key}-{slug(dim)}"]
            dim_uris[dim] = dim_uri
            graph.add((dim_uri, RDF.type, KPI.GranularityDimension))
            graph.add((dim_uri, KPI.dimensionLabel, Literal(dim)))
            graph.add((dim_uri, KPI.granularityPropertyURI, Literal(DATA_ONTOLOGY_NS + dim, datatype=XSD.anyURI)))
            graph.add((kpi_uri, KPI.hasGranularityDimension, dim_uri))

        for index, row in enumerate(result["all_rows"], start=1):
            result_uri = INST[f"result-{spec.key}-{index:03d}"]
            graph.add((result_uri, RDF.type, KPI.AggregationResult))
            graph.add((result_uri, KPI.aggregationValue, decimal_literal(row["value"])))
            graph.add((kpi_uri, KPI.hasAggregationResult, result_uri))
            for dim in spec.dimensions:
                dv_uri = INST[f"dv-{spec.key}-{index:03d}-{slug(dim)}"]
                graph.add((dv_uri, RDF.type, KPI.DimensionValue))
                graph.add((dv_uri, KPI.forDimension, dim_uris[dim]))
                graph.add((dv_uri, KPI.dimensionValueLiteral, Literal(str(row[dim]))))
                graph.add((result_uri, KPI.hasDimensionValue, dv_uri))
    return graph


def validate_kpis(kpi_graph: Graph, shapes_path: Path) -> Dict[str, object]:
    if shacl_validate is None:
        return {"available": False, "conforms": None, "message": "pyshacl is not installed"}
    validation_data = Graph()
    for triple in kpi_graph:
        validation_data.add(triple)
    validation_data.parse(shapes_path, format="turtle")
    conforms, report_graph, report_text = shacl_validate(
        data_graph=validation_data,
        shacl_graph=str(shapes_path),
        ont_graph=str(shapes_path),
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    return {
        "available": True,
        "conforms": bool(conforms),
        "report_triples": len(report_graph),
        "message": report_text.strip().splitlines()[:20],
    }


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def write_report(path: Path, report: Dict[str, object]) -> None:
    alignment = report["alignment"]
    conformance = report["schema_conformance"]
    summary = report["dataset_summary"]
    queries = report["kpi_queries"]

    rows = [
        ["Instance triples", summary["triples"]],
        ["Ontology triples", report["ontology_triples"]],
        ["Classes with instances", summary["classes_with_instances"]],
        ["KPI specifications executed", len(queries)],
        ["Generated KPI result rows", sum(q["row_count"] for q in queries)],
        ["Generated KPI triples", report["generated_kpi_triples"]],
        ["SHACL conforms", report["shacl_validation"]["conforms"]],
    ]
    coverage_rows = [
        ["Used classes", alignment["used_classes"]],
        ["Used properties", alignment["used_properties"]],
        ["Exact URI class matches", alignment["exact_class_matches"]],
        ["Exact URI property matches", alignment["exact_property_matches"]],
        ["Local-name class matches", alignment["local_class_matches"]],
        ["Local-name property matches", alignment["local_property_matches"]],
    ]
    query_rows = [
        [
            q["label"],
            q["operator"],
            q["aggregation_property"],
            ", ".join(q["dimensions"]),
            q["row_count"],
            q["elapsed_ms"],
        ]
        for q in queries
    ]

    top_classes = [
        [row["class"], row["count"]] for row in summary["top_class_counts"]
    ]

    text = [
        "# FIFA World Cup 2026 KPI Evaluation",
        "",
        "## Summary",
        markdown_table(["Metric", "Value"], rows),
        "",
        "## Dataset Profile",
        markdown_table(["Class", "Instances"], top_classes),
        "",
        "## Ontology/Data Correspondence",
        markdown_table(["Check", "Value"], coverage_rows),
        "",
        "The packaged ontology and instance data use the same football ontology namespace. "
        "The correspondence check reports the exact vocabulary overlap used for selecting "
        "the KPI subset.",
        "",
        f"Domain triples checked: {conformance['checked_domain_triples']}.",
        f"Range triples checked: {conformance['checked_range_triples']}.",
        f"Domain violations: {conformance['domain_violation_count']}.",
        f"Range violations: {conformance['range_violation_count']}.",
        f"Functional property violations: {conformance['functional_property_violations']}.",
        "",
        "## KPI Query Results",
        markdown_table(
            ["KPI", "Operator", "Aggregation property", "Dimension", "Rows", "Time ms"],
            query_rows,
        ),
        "",
        "## Sample Result Rows",
    ]
    for q in queries:
        sample = q["sample_rows"][:5]
        headers = list(sample[0].keys()) if sample else []
        text.extend(["", f"### {q['label']}"])
        if sample:
            text.append(markdown_table(headers, [[row[h] for h in headers] for row in sample]))
        else:
            text.append("(no rows)")

    text.extend(
        [
            "",
            "## Notes For The Paper",
            "",
            "- The experiment demonstrates that the reference workflow can be applied outside the HR toy example.",
            "- It covers same-class dimensions and one-hop object-property joins.",
            "- The KPI definitions use the ontology/data overlap; role-model terms can be added to broaden coverage.",
            "- The generated KPI Turtle was checked against the KPI ontology SHACL shapes.",
            "",
        ]
    )
    path.write_text("\n".join(text), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ontology", type=Path, default=ONTOLOGY_FILE)
    parser.add_argument("--instances", type=Path, default=INSTANCES_FILE)
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--kpi-shapes", type=Path, default=DEFAULT_KPI_SHAPES)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for path in [args.ontology, args.instances, args.kpi_shapes]:
        if not path.exists():
            print(f"Missing required file: {path}", file=sys.stderr)
            return 2

    ontology, ontology_load_s = parse_graph(args.ontology)
    instances, instances_load_s = parse_graph(args.instances)

    alignment = check_alignment(ontology, instances)
    schema_conformance = check_schema_conformance(ontology, instances)
    summary = dataset_summary(instances)
    kpi_queries = run_kpi_queries(instances)
    kpi_graph = materialize_kpis(kpi_queries, stable_input_uri(args.instances))
    kpi_ttl_path = args.out_dir / "fifa2026_kpi_instances.ttl"
    kpi_graph.serialize(kpi_ttl_path, format="turtle")
    shacl_report = validate_kpis(kpi_graph, args.kpi_shapes)

    for old_csv in args.out_dir.glob("*.csv"):
        old_csv.unlink()
    for query_result in kpi_queries:
        write_csv(args.out_dir / f"{query_result['key']}.csv", query_result["all_rows"])

    report = {
        "inputs": {
            "ontology": display_path(args.ontology),
            "instances": display_path(args.instances),
            "kpi_shapes": display_path(args.kpi_shapes),
        },
        "ontology_triples": len(ontology),
        "instance_triples": len(instances),
        "ontology_load_s": round(ontology_load_s, 3),
        "instances_load_s": round(instances_load_s, 3),
        "alignment": alignment,
        "schema_conformance": schema_conformance,
        "dataset_summary": summary,
        "kpi_queries": kpi_queries,
        "generated_kpi_triples": len(kpi_graph),
        "generated_kpi_ttl": display_path(kpi_ttl_path),
        "shacl_validation": shacl_report,
    }
    json_path = args.out_dir / "fifa2026_kpi_evaluation.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(args.out_dir / "fifa2026_kpi_evaluation.md", report)

    print(f"Wrote {display_path(json_path)}")
    print(f"Wrote {display_path(args.out_dir / 'fifa2026_kpi_evaluation.md')}")
    print(f"Wrote {display_path(kpi_ttl_path)}")
    print(f"Loaded {len(instances)} instance triples in {instances_load_s:.2f}s")
    print(f"Executed {len(kpi_queries)} KPI queries with {sum(q['row_count'] for q in kpi_queries)} result rows")
    print(f"SHACL conforms: {shacl_report['conforms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
