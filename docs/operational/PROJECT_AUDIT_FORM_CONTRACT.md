# Universal project audit form

Sentinel audits one explicitly configured Central project at a time. The
same Sentinel code and the same audit form can be used on any Central install;
only Central connection settings, the project allowlist, and the published
audit-form identifier are configuration.

The current universal form is [audit_001_v5.xlsx](../odk_forms/audit/audit_001_v5.xlsx).
Publish it once in each audited project. Sentinel needs read permission on the
project's source forms and submit permission on this audit form. It never edits
or deletes source submissions.

When version 5 is published, set `audit_form_id` and `audit_form_version` in
the local Sentinel configuration. Version 5 contains the ledger and batch
timestamp fields, dedicated JSON/PDF fields for project health, project users
and roles, privileged admin snapshots and validation certificates, and a
generic ZIP evidence-package field. It does not contain a source-data bundle
field.

The dedicated evidence attachment fields are:

| Form field | Filename | Purpose |
|---|---|---|
| `timestamp_manifest` | `timestamp_manifest.json` | Run manifest |
| `timestamp_token` | `timestamp_token.tsr` | RFC3161 timestamp token |
| `timestamp_certificate` | `timestamp_certificate.pem` | TSA certificate |
| `project_health_snapshot` | `project_health_snapshot.json` | Machine-readable project health snapshot |
| `project_health_snapshot_pdf` | `project_health_snapshot.pdf` | Human-readable project health snapshot |
| `project_user_roles_snapshot` | `project_user_roles_snapshot.json` | Machine-readable project users and roles snapshot |
| `project_user_roles_snapshot_pdf` | `project_user_roles_snapshot.pdf` | Human-readable project users and roles snapshot |
| `admin_platform_snapshot` | `admin_platform_snapshot.json` | Machine-readable privileged platform snapshot |
| `admin_platform_snapshot_pdf` | `admin_platform_snapshot.pdf` | Human-readable privileged platform snapshot |
| `validation_report` | `validation_report.json` | Machine-readable validation report |
| `validation_certificate` | `validation_certificate.pdf` | Human-readable validation certificate |
| `evidence_package` | `evidence_package.zip` | Complete JSON/PDF/raw-evidence bundle |

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
| `project_health_snapshot` | Non-participant project/API inventory observed during one Sentinel run |
| `project_user_roles_snapshot` | Project-visible Web User and role-assignment inventory observed during one Sentinel run |
| `admin_platform_snapshot` | Privileged, time-scoped Central administration and platform snapshot |

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

Every run carries the validation report and human-readable certificate on the
same `run_timestamp_manifest` record. The report includes deterministic-ID
uniqueness, planned-versus-processed reconciliation, manifest-chain status and
timestamp status.

The active validation certificate contains twenty automated checks. Its PDF
`evidence_ref` values point to concrete raw files inside
`evidence_package.zip`, rather than merely pointing to the summary JSON. The
package includes the form definition, original and edited XML, retained
version metadata, diffs, Central audit events, comments, attachment inventory,
submission metadata, Sentinel scope/plan evidence and the hash manifest.

The same form also stores one deterministic project checkpoint record. A new
run reads that checkpoint and the existing audit-form submissions before
fetching work, so completed versions are not repeated.

No project-specific field names, participant fields, XLSForm recipes, or
MethodMesh attestation payloads are required.

Each run carries a `project_health_snapshot.json` and PDF, plus a
`project_user_roles_snapshot.json` and PDF, on that same run record. The health
snapshot records project metadata and source-form/submission inventory. The
user-role snapshot records the Web Users visible to the regular account, role
definitions and current project assignments. If Central does not grant one of
these reads, the snapshot records that limitation explicitly rather than
treating the data as complete. Neither claims to measure server disk space,
uptime, CPU, memory or backups; those metrics belong to separately privileged
Admin Sentinel.

An explicitly invoked Admin Sentinel run creates one
`admin_platform_snapshot` record. It uses the existing `platform_snapshot`,
`platform_snapshot_pdf` and `evidence_package` attachment fields, so no
audit-form redesign is required. See [Admin Sentinel](ADMIN_SENTINEL.md).

The server-wide Central audit feed is not required for the basic workflow. If
enabled with `server_audit_enabled`, it requires a Server Administrator account
and is intended for additional forensic oversight, not routine source-data
integrity. Central does not generally emit ordinary web logout events.
