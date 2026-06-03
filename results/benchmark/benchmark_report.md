# GovDataContractBench Initial Results

- Cases: 14561
- By artifact type: {'ckan': 5000, 'fhir': 8726, 'openapi': 835}
- By label: {'breaking_provenance': 4000, 'breaking_schema': 4430, 'non_breaking': 3003, 'breaking_semantic': 3012, 'breaking_security': 116}

## Overall Detector Metrics

| Detector | Precision | Recall | F1 | Severity-weighted recall | Runtime ms/case |
|---|---:|---:|---:|---:|---:|
| parser_only | 0.0 | 0.0 | 0.0 | 0.0 | 0.046868 |
| structural_required | 1.0 | 0.6602 | 0.7954 | 0.6293 | 0.003562 |
| structural_plus_semantic | 1.0 | 0.8993 | 0.947 | 0.9232 | 0.021527 |
| compatibility | 1.0 | 0.7547 | 0.8602 | 0.6997 | 0.003292 |
| proposed_multilayer | 1.0 | 0.9938 | 0.9969 | 0.9936 | 0.01059 |

## Recall By Label

| Detector | Label | Cases | Recall | Severity-weighted recall |
|---|---|---:|---:|---:|
| parser_only | breaking_provenance | 4000 | 0.0 | 0.0 |
| parser_only | breaking_schema | 4430 | 0.0 | 0.0 |
| parser_only | breaking_security | 116 | 0.0 | 0.0 |
| parser_only | breaking_semantic | 3012 | 0.0 | 0.0 |
| parser_only | non_breaking | 3003 | 0.0 | 0.0 |
| structural_required | breaking_provenance | 4000 | 0.988 | 0.988 |
| structural_required | breaking_schema | 4430 | 0.7743 | 0.7743 |
| structural_required | breaking_security | 116 | 0.0 | 0.0 |
| structural_required | breaking_semantic | 3012 | 0.0827 | 0.0827 |
| structural_required | non_breaking | 3003 | 0.0 | 0.0 |
| structural_plus_semantic | breaking_provenance | 4000 | 0.988 | 0.988 |
| structural_plus_semantic | breaking_schema | 4430 | 0.7743 | 0.7743 |
| structural_plus_semantic | breaking_security | 116 | 0.0 | 0.0 |
| structural_plus_semantic | breaking_semantic | 3012 | 1.0 | 1.0 |
| structural_plus_semantic | non_breaking | 3003 | 0.0 | 0.0 |
| compatibility | breaking_provenance | 4000 | 0.988 | 0.988 |
| compatibility | breaking_schema | 4430 | 0.9946 | 0.9946 |
| compatibility | breaking_security | 116 | 1.0 | 1.0 |
| compatibility | breaking_semantic | 3012 | 0.0827 | 0.0827 |
| compatibility | non_breaking | 3003 | 0.0 | 0.0 |
| proposed_multilayer | breaking_provenance | 4000 | 0.988 | 0.988 |
| proposed_multilayer | breaking_schema | 4430 | 0.9946 | 0.9946 |
| proposed_multilayer | breaking_security | 116 | 1.0 | 1.0 |
| proposed_multilayer | breaking_semantic | 3012 | 1.0 | 1.0 |
| proposed_multilayer | non_breaking | 3003 | 0.0 | 0.0 |