# Project validation forms

These four XLSForms are reusable synthetic-data fixtures. Publish them in
each project that will be routinely validated:

- `sentinel_validation_central.xlsx` - Central/API submission, edit, version,
  reason and Sentinel-detection checks.
- `sentinel_validation_enketo.xlsx` - tightly scoped Enketo rendering, entry,
  edit and reason checks.
- `sentinel_validation_collect.xlsx` - tightly scoped Collect device, audit,
  offline and synchronization checks.
- `sentinel_validation_methodmesh.xlsx` - NFC identity, attestation, clock
  and time-assurance checks.

They contain synthetic test fields only. They are not participant forms and
must not be used for study data.

## Sentinel configuration

List the published XML form IDs in the project configuration:

```json
{
  "validation_form_ids": [
    "sentinel_validation_central",
    "sentinel_validation_enketo",
    "sentinel_validation_collect",
    "sentinel_validation_methodmesh"
  ]
}
```

Sentinel excludes these forms from ordinary source archiving and from
project-filtered Central lifecycle events. The validation runner can use them
as controlled fixtures without treating their synthetic records as study
source data.

Keep the forms small. The Central form is the broadest API fixture; the
Enketo and Collect forms deliberately test only the user-facing behaviors that
cannot be inferred from Central alone. The MethodMesh form records the
synthetic operation and returned identity/attestation evidence without
including participant identifiers.
