# ODK forms

This folder contains the ODK/XLSForm artifacts used by the current Sentinel
implementation.

- `audit/` - Sentinel audit-form workbooks and the XML reference.
- `validation/` - the four synthetic Central, Enketo, Collect and MethodMesh
  validation forms.
The validation forms are synthetic fixtures only. Do not use them for
participant or study data.

The current architecture is defined by the repository `README.md`,
`docs/SENTINEL_USER_GUIDE.md`, `docs/ARCHIVAL_BASELINE.md` and the operational
audit-form contract. The former root-level Sentinel Master Book and the old
MethodMesh compiler/example tree were removed
because it described a superseded platform and canonical-payload architecture.
