# Universal project audit form

Sentinel audits one explicitly configured Central project at a time. The
same Sentinel code and the same audit form can be used on any Central install;
only Central connection settings, the project allowlist, and the published
audit-form identifier are configuration.

The current universal form is [audit_001_v2.xlsx](audit_001_v2.xlsx).
Publish it once in each audited project. Sentinel needs read permission on the
project's source forms and submit permission on this audit form. It never edits
or deletes source submissions.

When version 2 is published, set `audit_form_id` and `audit_form_version` in
the local Sentinel configuration. Version 2 contains the ledger fields and batch
timestamp fields, including the RFC3161 token upload. It does not contain a
source-data bundle field.

## One project-level ledger

Every source form and every retained Central submission version is represented
by one audit-form submission. The deterministic audit instance ID is derived
from:

```text
project_id + source_form_id + logical_instance_id + source_version_id
```

The audit record contains the source identifiers, exact-byte hashes, Central
metadata, linked audit event/reason information and timestamp evidence. The
original source data remains in Central and is referenced by its original
submission UUID; Sentinel does not copy it into the audit form.

`record_type` is deliberately human-readable:

| Value | Meaning |
|---|---|
| `source_form_version` | A published version of a source form |
| `original_submission` | The original retained Central submission version |
| `submission_edit` | A later retained Central edit of that submission |
| `central_*` | Optional project-filtered Central server-audit event; disabled by default |
| `project_checkpoint` | The crawl checkpoint for the configured project |
| `run_timestamp_manifest` | The manifest covering one Sentinel run |
| `validation_certificate` | Automated validation and reconciliation results for one Sentinel run |

Each run also creates a `run_timestamp_manifest` record. Its
`timestamp_batch_sha256` is the SHA-256 of the attached `timestamp_manifest.json`,
and `timestamp_batch_id` links the audit record to the manifest and to the
`sentinel_run_id` values on records processed in that run. Sentinel sends only
the manifest hash to the configured RFC3161 authority. If the preferred TSA
call is unavailable, the manifest is still preserved and its status is
explicitly `manifest_created_not_timestamped`; a required policy fails the run
instead.

Manifests carry the previous manifest's audit-record ID and hash. This creates
a run-level, timestamp-anchored chain that can expose an altered or missing
intermediate manifest. It is deliberately not a `previous_attestation_hash`
chain on every source record.

Every run also creates a `validation_certificate` record. Its
`validation_certificate.json` attachment contains the checks performed during
the run, including deterministic-ID uniqueness, planned-versus-processed
reconciliation, manifest-chain status and timestamp status. The certificate
has its own hash and timestamp evidence.

The same form also stores one deterministic project checkpoint record. A new
run reads that checkpoint and the existing audit-form submissions before
fetching work, so completed versions are not repeated.

No project-specific field names, participant fields, XLSForm recipes, or
MethodMesh attestation payloads are required.

The server-wide Central audit feed is not required for the basic workflow. If
enabled with `server_audit_enabled`, it requires a Server Administrator account
and is intended for additional forensic oversight, not routine source-data
integrity. Central does not generally emit ordinary web logout events.
