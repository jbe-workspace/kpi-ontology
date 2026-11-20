# FIFA World Cup 2026 KPI Evaluation

## Summary
| Metric | Value |
| --- | --- |
| Instance triples | 137347 |
| Ontology triples | 816 |
| Classes with instances | 30 |
| KPI specifications executed | 6 |
| Generated KPI result rows | 96 |
| Generated KPI triples | 732 |
| SHACL conforms | True |

## Dataset Profile
| Class | Instances |
| --- | --- |
| Role | 7112 |
| PlayerRole | 6574 |
| MatchPlayerRole | 5325 |
| MatchEvent | 1583 |
| Person | 1429 |
| SquadMembershipRole | 1249 |
| Substitution | 989 |
| Goal | 308 |
| RefereeRole | 304 |
| Booking | 286 |
| CoachRole | 234 |
| HeadCoachRole | 234 |
| MatchTeamStatistics | 208 |
| AssistantRefereeRole | 202 |
| MatchCoachRole | 186 |

## Ontology/Data Correspondence
| Check | Value |
| --- | --- |
| Used classes | 30 |
| Used properties | 122 |
| Exact URI class matches | 17 |
| Exact URI property matches | 95 |
| Local-name class matches | 17 |
| Local-name property matches | 95 |

The packaged ontology and instance data use the same football ontology namespace. The correspondence check reports the exact vocabulary overlap used for selecting the KPI subset.

Domain triples checked: 35274.
Range triples checked: 36856.
Domain violations: 13128.
Range violations: 4683.
Functional property violations: 0.

## KPI Query Results
| KPI | Operator | Aggregation property | Dimension | Rows | Time ms |
| --- | --- | --- | --- | --- | --- |
| Total goals scored by group | Sum | goalsFor | groupName | 12 | 6.27 |
| Number of matches by tournament stage | Count | stage | stage | 7 | 4.96 |
| Average attendance by tournament stage | Average | attendance | stage | 6 | 4.82 |
| Number of matches by venue | Count | playedAtVenue | venueName | 16 | 6.78 |
| Average shots per match-team record by team | Average | shotsTotal | teamName | 48 | 15.24 |
| Average home-win odds by tournament stage | Average | oddsHomeWin | stage | 7 | 6.77 |

## Sample Result Rows

### Total goals scored by group
| groupName | value |
| --- | --- |
| Group A | 12 |
| Group B | 22 |
| Group C | 16 |
| Group D | 15 |
| Group E | 17 |

### Number of matches by tournament stage
| stage | value |
| --- | --- |
| FINAL | 1 |
| GROUP_STAGE | 72 |
| QUARTER_FINALS | 4 |
| ROUND_OF_16 | 8 |
| ROUND_OF_32 | 16 |

### Average attendance by tournament stage
| stage | value |
| --- | --- |
| FINAL | 80663.0 |
| GROUP_STAGE | 63542.625 |
| QUARTER_FINALS | 67151.5 |
| ROUND_OF_16 | 70555.75 |
| ROUND_OF_32 | 60919.0 |

### Number of matches by venue
| venueName | value |
| --- | --- |
| AT&T Stadium | 9 |
| Mercedes-Benz Stadium | 8 |
| MetLife Stadium | 8 |
| SoFi Stadium | 8 |
| BC Place | 7 |

### Average shots per match-team record by team
| teamName | value |
| --- | --- |
| Turkey | 23.666666666666668 |
| Colombia | 19.2 |
| Belgium | 18.5 |
| Germany | 18.5 |
| Senegal | 18.0 |

### Average home-win odds by tournament stage
| stage | value |
| --- | --- |
| FINAL | 2.31 |
| GROUP_STAGE | 3.667638888888889 |
| QUARTER_FINALS | 2.1925 |
| ROUND_OF_16 | 4.68375 |
| ROUND_OF_32 | 2.115 |

## Notes For The Paper

- The experiment demonstrates that the reference workflow can be applied outside the HR toy example.
- It covers same-class dimensions and one-hop object-property joins.
- The KPI definitions use the ontology/data overlap; role-model terms can be added to broaden coverage.
- The generated KPI Turtle was checked against the KPI ontology SHACL shapes.
