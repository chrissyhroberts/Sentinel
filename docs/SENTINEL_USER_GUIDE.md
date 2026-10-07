# Sentinel user guide and continuation brief

This is the self-contained starting point for operating Sentinel or continuing
its development in a new chat. Read this before changing code, forms,
configuration or the evidence model.

## 1. Purpose and current release

Sentinel is a project-scoped integrity ledger for ODK Central. For one
explicitly configured project it discovers source forms, published form
versions, logical submissions and retained Central versions; retrieves exact
XML bytes; reads Central diffs, audit events, comments and reasons; hashes the
retrieved bytes; and writes deterministic references to the project audit form.

The source data remains in Central. Sentinel is not a second participant-data
repository and does not copy source submissions into the audit form.

Repository: <https://github.com/chrissyhroberts/Sentinel>

Current release: `v0.3.0`.

## 2. Non-negotiable architecture

### Central is the source repository

ODK Central retains the original submission, edits, Collect audit trail,
attachments and Central audit metadata. Sentinel stores hashes, identifiers,
references, reports and evidence attachments in the audit form.

Do not redesign Sentinel into a local research archive or copy participant
records into the audit form.

### MethodMesh does not hash the whole form payload

The earlier whole-record canonical-hash/recipe approach was too difficult to
author and maintain. It is not the target architecture.

MethodMesh should attest a simple, stable object:

- ODK submission UUID;
- form/version context where available;
- NFC credential and verification execution;
- PIN verification, or optional local OS biometric verification;
- device/execution state and monotonic evidence;
- local time-assurance state; and
- RFC3161 timestamp when available and required by policy.

It must not reconstruct or concatenate every source field. Sentinel hashes the
exact XML retained by Central after receipt.

### Three separate provenance controls

1. NFC/PIN identifies use of a controlled credential.
2. MethodMesh attests the UUID and identity evidence.
3. Sentinel hashes and archives the exact Central record/version.

NFC plus a memorised PIN is possession plus knowledge across separate factors.
It does not constitute biometric proof of the named person unless additional
controls support that claim. If phone fingerprint is added, it should remain
local OS-level verification; MethodMesh should receive a signed `user verified`
result, never a fingerprint template.

### Trusted time is not backdating

`timestamp_policy: preferred` is the normal policy.

- RFC3161 available: Sentinel timestamps the run-manifest hash.
- RFC3161 unavailable: Sentinel retains the manifest with explicit
  `manifest_created_not_timestamped` status.
- A later RFC3161 timestamp proves the manifest existed by that later trusted
  time; it does not backdate data entry.
- A monotonic clock provides sequence/elapsed-time evidence, not independent
  trusted wall-clock time.

Do not fail the whole run for a temporary TSA outage unless the study risk
assessment explicitly requires `timestamp_policy: required`.

## 3. Repository layout

```text
sentinel_archive/                         Python implementation
tests/                                    Automated tests
docs/ARCHIVAL_BASELINE.md                 Evidence boundary
docs/operational/                         Operating procedures/contracts
docs/validation/                          Validation plans/checklists
docs/odk_forms/audit/audit_001_v6.xlsx    Current universal audit form
docs/odk_forms/validation/                Synthetic validation forms
README.md                                 Quick-start documentation
CHANGELOG.md                              Release history
```

The MethodMesh compiler material under `docs/odk_forms/methodmesh_examples/`
contains earlier/legacy material. Do not silently restore the old frozen
whole-payload commitment as the new Sentinel contract.

## 4. Central setup

Publish `docs/odk_forms/audit/audit_001_v6.xlsx` in the audited project. The
form ID and version are configuration values; the tested project uses form ID
`audit_001` and version `6`.

The regular Sentinel account needs read access to the project and source forms,
read access to permitted submission/version evidence, and submit access to the
audit form. It must not need permission to edit or delete source submissions.

Publish these synthetic forms in projects that will be routinely validated:

- `sentinel_validation_central`
- `sentinel_validation_enketo`
- `sentinel_validation_collect`
- `sentinel_validation_methodmesh`

They contain synthetic test fields only and must remain outside study source
scope.

## 5. Local configuration

Keep configuration outside Git, normally at `.sentinel-local/sentinel.config`:

```json
{
  "base_url": "https://central.example.org",
  "project_id": "239",
  "email": "sentinel@example.org",
  "audit_form_id": "audit_001",
  "audit_form_version": "6",
  "timestamp_policy": "preferred",
  "timestamp_url": "https://tsr.open-tsa.eu",
  "token_env": "ODK_CENTRAL_TOKEN",
  "validation_form_ids": [
    "sentinel_validation_central",
    "sentinel_validation_enketo",
    "sentinel_validation_collect",
    "sentinel_validation_methodmesh"
  ],
  "server_audit_enabled": false
}
```

Important settings:

| Setting | Meaning |
|---|---|
| `project_id` | One explicitly audited Central project; the number in `/projects/239/` is the ID. |
| `audit_form_id` | Published universal audit form. |
| `audit_form_version` | Published audit form version; use `6` for `audit_001_v6.xlsx`. |
| `timestamp_policy` | `preferred`, `required` or `disabled`; use `preferred` normally. |
| `timestamp_url` | RFC3161 TSA endpoint. |
| `validation_form_ids` | Synthetic IDs excluded from source archiving. |
| `server_audit_enabled` | Optional privileged Central-wide audit feed; normally `false`. |
| `admin_email` | Administrator account used only with `--admin-validate`. |
| `admin_project_ids` | Projects included in monthly admin evidence. |

Passwords should be entered interactively or supplied through the configured
environment variable. Never commit credentials, tokens or a real config file.

## 6. Commands

Run from the repository root.

### Normal daily run

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --debug
```

Discovers pending work, archives new form/submission versions, creates daily
snapshots and submits the consolidated QA line.

### Plan only

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --plan-only
```

Reads Central and reports planned scope without submitting records.

### Read-only validation

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate
```

Validates project/configuration without creating or editing source data.

### Active synthetic validation

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate-active --debug
```

Uses only the Central validation form. It creates/edits synthetic data, checks
versions, diffs, reasons, actor evidence and attachments, and creates/deletes a
disposable validation form. It must never touch a study source form.

### Privileged monthly run

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --admin-validate
```

Prompts for the administrator password and collects permitted administrative
evidence. Host disk space, uptime and similar metrics require a separately
supplied host snapshot; they are not inferred from the ordinary project API.

### Download one raw submission XML

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config \
  --download-xml FORM_ID INSTANCE_ID OUTPUT.xml
```

For a complete source export, use
`docs/operational/VERIFY_AND_EXPORT_SOURCE_XML.md`.

## 7. What Sentinel writes to Central

### Form versions

Each published source-form version gets a `source_form_version` row containing
the deployed XML hash. On audit form version 6 or later it also attaches:

- `source_form_definition.xml` — exact deployed Central XForm XML;
- `source_form_definition.xlsx` — original XLSForm workbook when Central
  retains an Excel source.

### Submission versions

Each original submission gets `original_submission`. Each later Central edit
gets `submission_edit`. Records include source form ID, logical submission UUID,
Central version ID, exact XML hash, Collect audit hash where available, Central
actor/timestamps, old/new diffs, and linked Central change reason where
available.

### Consolidated daily QA row

Each run creates one `sentinel_run_qa_snapshot` line carrying the timestamp
manifest, project health, user/role snapshot, validation report/certificate,
QA PDF and evidence package. Summaries belong here; discrete changes get their
own audit row.

### Optional event rows

When `server_audit_enabled` is true and permissions allow it, relevant Central
lifecycle events may receive `central_*` rows, including form, user,
assignment, public-link, submission and deletion/restoration events. This is
optional because it commonly requires Server Administrator access.

## 8. Output files

The consolidated QA row uses dedicated attachment fields:

| File | Contents |
|---|---|
| `timestamp_manifest.json` | Records processed, hashes, run identity, previous-manifest reference and timestamp status. |
| `timestamp_token.tsr` | RFC3161 response when available. |
| `timestamp_certificate.pem` | TSA certificate when extracted. |
| `project_health_snapshot.json` | Detailed project/API inventory and chain reconciliation. |
| `sentinel_qa_summary.pdf` | Human-readable daily progress/governance report. |
| `project_user_roles_snapshot.json` | Current project users, actor IDs, roles and assignments. |
| `project_user_roles_snapshot.pdf` | Human-readable user/role report. |
| `validation_report.json` | Machine-readable validation results. |
| `validation_certificate.pdf` | Human-readable validation certificate. |
| `evidence_package.zip` | Raw validation evidence plus SHA-256 evidence manifest. |
| `source_form_definition.xml` | Exact deployed source form XML on a form-version row. |
| `source_form_definition.xlsx` | Original source XLSForm when available on a form-version row. |

Local validation copies are under `.sentinel-local/validation/`; Central is the
retained evidence boundary.

## 9. Run-manifest chain reconciliation

The chain is run-level only. It is not a chain over every submission and does
not use `previous_attestation_hash`.

Every run manifest points to the preceding manifest's audit instance ID and
manifest hash. Each regular run reconstructs the retained chain backwards from
the latest manifest and reports:

- `genesis` — no previous manifest exists;
- `intact` — all links resolve and hashes agree;
- `intact_with_orphans` — latest chain is intact but older rows are not linked;
- `broken` — a row is missing, unreadable, cyclic or has a hash mismatch.

The report includes the first affected timepoint, expected row ID, expected
hash and reason where available. It appears in the JSON health snapshot, QA PDF
and validation certificate. Source reconciliation separately compares planned
source tasks with existing/new deterministic audit rows.

## 10. Attribution and time interpretation

NFC plus PIN should be described as controlled credential attribution:

> A valid NFC credential and knowledge of its PIN were used for this operation.

It is not automatically proof that a named human was physically present unless
credential issuance, custody, PIN secrecy, revocation and anti-sharing controls
support that claim.

MethodMesh binds UUID and identity execution evidence. Sentinel binds that UUID
to the exact Central XML/version and Central actor/timestamp metadata.

For offline Collect, local time is provisional/non-trusted. Do not manufacture
a trusted timestamp. When connectivity returns, Sentinel can timestamp the
resulting manifest or later Central receipt window.

## 11. Validation model

Validation is split into five components:

- ODK Central — API, permissions, forms, submissions, versions, diffs and
  lifecycle behavior;
- ODK Collect — device entry, audit trail, offline queue and synchronization;
- Enketo — rendering, entry, edit and reason behavior;
- MethodMesh — NFC identity, UUID attestation, clock and time assurance;
- Sentinel — crawl, hashing, idempotency, evidence, timestamps and chain.

Passing Central validation does not validate Collect, Enketo or MethodMesh.
Use the four synthetic forms and checklists under `docs/validation/`.

## 12. Current ALCOA+ gaps

Sentinel is strong on Central-side provenance. Remaining upstream priorities:

1. Credential issuance, replacement, expiry and revocation.
2. PIN confidentiality, failed-attempt handling and anti-sharing procedures.
3. Explicit UUID binding between Collect, MethodMesh and Central.
4. Offline queue, retry, duplicate and device-replacement behavior.
5. Device lock, encryption, supported versions, updates and backup controls.
6. MethodMesh key custody, rotation, revocation and independent verification.
7. Negative tests for replay, altered UUID, revoked credential, altered
   evidence and clock rollback.
8. Controlled validation, SOPs, change control and periodic revalidation.
9. Recovery/restore testing and long-term retention/readability.

The bounded plan is
`docs/validation/METHODMESH_SENTINEL_GAP_CLOSURE.md`.

## 13. Troubleshooting

### `404 form version specified ... does not exist`

`audit_form_version` does not match the published audit form. Inspect Central's
current version and update the local config.

### `400 Length of value too long for a field`

A scalar field exceeded Central's length limit. Keep scalar fields short and
put detailed material in its dedicated attachment field.

### Enketo says `Invalid XML source`

Inspect raw XML through the Central API. The root `data` ID must match the audit
form ID and the XML must contain `orx:meta/instanceID`. Do not diagnose from
the Central table alone.

### `403` resolving actor email

The regular account may see an actor ID but not be allowed to read the Central
user record. Preserve the actor ID; email enrichment is optional.

### `500` on attachment-heavy submission

Confirm the audit form version has the matching `file` fields and that the XML
uses the exact audit form ID/version. Keep JSON/PDF content in attachments,
not scalar fields.

### Interrupted run

Run the same command again. Existing deterministic rows are skipped and pending
versions resume. Do not delete the audit form or records to force a repeat.

## 14. Safe continuation protocol

A new chat must first:

1. confirm the repository is `/Users/icrucrob/Documents/GitHub/Sentinel`;
2. read this guide, `README.md`, `docs/ARCHIVAL_BASELINE.md` and the relevant
   operational/validation document;
3. inspect `git status`, recent commits and the current tag;
4. run the test suite before changing behavior;
5. preserve the UUID-level MethodMesh boundary and Central storage boundary;
6. never replace the architecture with a whole-record MethodMesh recipe;
7. avoid staging `.DS_Store`, generated egg-info or user study files;
8. make changes with tests and update documentation; and
9. report exactly what changed, tested, committed and pushed.

The next priority is a risk-based ALCOA+ closure plan for ODK Collect and
MethodMesh, not a redesign of Sentinel's archival model.
