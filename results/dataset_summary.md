# Dataset Summary

## apis_guru

- `status`: ok
- `downloaded_specs`: 150
- `target_keyword_specs`: 150
- `json_parsed_specs`: 150
- `yaml_or_text_specs`: 0
- `total_paths_heuristic`: 2887
- `median_paths_heuristic`: 5.5
- `total_schemas_heuristic`: 16074
- `median_schemas_heuristic`: 41.0
- `specs_with_security_schemes`: 116
- `required_occurrences`: 14633
- `enum_occurrences`: 5604

## open_gov_ckan_metadata

- `source_api`: https://data.gov.au/data/api/3/action/package_search
- `retrieval_method`: fallback_ckan_package_search
- `status`: ok
- `records`: 10000
- `field_completeness`: {"title": 1.0, "notes": 1.0, "organization": 1.0, "metadata_modified": 1.0, "license_id": 1.0, "resources": 0.9885, "tags": 0.8268, "groups": 0.0432}
- `resource_total`: 52888
- `resource_url_completeness`: 0.9993
- `resource_format_completeness`: 0.9994
- `top_organizations`: [["geoscience-australia-data", 1987], ["australian-ocean-data-network", 1663], ["data-act", 494], ["city-moreton-bay-data-hub", 475], ["brisbane-city-council-queensland-government", 438], ["spatial-services-dcs-datansw", 369], ["nsw-department-of-climate-change-energy-the-environment-and-water-datansw", 352], ["act-government-geospatial-data-catalogue", 335], ["environment-tourism-science-and-innovation-queensland-government", 312], ["city-of-melbourne-open-data", 239]]
- `top_licenses`: [["notspecified", 4333], ["cc-by", 2004], ["other", 1520], ["cc-by-4", 895], ["cc-by-2.5", 276], ["cc-by-4.0", 197], ["custom_other", 197], ["custom_active_acceptance", 192], ["cc-by-sa", 125], ["cc-by-nc-nd-4.0", 82]]
- `top_resource_formats`: [["html", 16554], ["csv", 4124], ["zip", 3862], ["pdf", 3386], ["geojson", 2873], ["wms", 2762], ["wfs", 1739], ["png", 1472], ["shp", 1365], ["arcgis geoservices rest api", 1340], ["kml", 1298], ["xlsx", 1232], ["geotiff", 1005], ["json", 986], ["api arcgis server map service", 837]]

## fhir_us_core_examples

- `status`: ok
- `records`: 141
- `ids_present_rate`: 1.0
- `resource_types`: [["Observation", 114], ["Condition", 5], ["DiagnosticReport", 5], ["Patient", 5], ["MedicationRequest", 4], ["Encounter", 3], ["Medication", 2], ["Coverage", 1], ["MedicationDispense", 1], ["Provenance", 1]]
- `reference_occurrences`: 348

## smart_bulk_fhir_synthea_small

- `status`: ok
- `source_url`: https://github.com/smart-on-fhir/sample-bulk-fhir-datasets/archive/refs/heads/10-patients.zip
- `records`: 7887
- `ndjson_files`: 19
- `resource_types`: {"AllergyIntolerance": 11, "Condition": 298, "Device": 39, "DiagnosticReport": 780, "DocumentReference": 413, "Encounter": 413, "EpisodeOfCare": 413, "Immunization": 143, "Location": 44, "MedicationRequest": 172, "Observation": 2850, "Organization": 43, "Patient": 11, "Practitioner": 43, "PractitionerRole": 43, "Procedure": 1341, "ServiceRequest": 413, "Specimen": 413, "unknown": 4}
- `note`: Synthea-generated sample FHIR bulk export dataset from SMART-on-FHIR; small package contains 10 patients.
