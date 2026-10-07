# Sentinel
# MethodMesh Governance Sentinel

Sentinel is an integrity ledger and project audit service for ODK Central. It
records hashes and references for source-form versions, original submissions,
retained Central edits, change reasons and timestamp evidence. The source data
remains in ODK Central; Sentinel does not copy it into a second form. It does
not reconstruct canonical MethodMesh payloads from XLSForm recipes.

See [the archival baseline](docs/ARCHIVAL_BASELINE.md) for the governing
scope, evidence model and archive layout.

For independent verification or a complete retained XML export, see
[Verify and export source XML](docs/operational/VERIFY_AND_EXPORT_SOURCE_XML.md).

## Local configuration

The Central connection configuration is kept outside Git at:

```text
.sentinel-local/sentinel.config
```

Run Sentinel from the repository root with:

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --debug
```

The directory is gitignored. A normal run can use the regular account with an
interactive password prompt, `password_env`, or a locally stored `password`.
The privileged admin run always prompts for its administrator password.

The audit boundary is always one explicitly configured Central project. See
the [universal project audit form contract](docs/operational/PROJECT_AUDIT_FORM_CONTRACT.md).

Operational procedures are in [docs/operational](docs/operational/). The
risk-based validation checklist and workflow are in
[docs/validation](docs/validation/).

The current test form is `audit_001`, version 5. The form ID and version are
configuration values, so the same code can be used with a universal audit form
on another Central installation.

The implementation is in `sentinel_archive/`. It downloads exact submission
versions, Collect audit attachments, Central diffs and Central audit metadata,
then submits hashes and readable references to the configured audit form. The
original XML and attachments remain in Central.

## Default audit scope

For the configured project, one run records:

- deployed source-form versions;
- original submissions and every retained Central edit;
- field-level edit diffs, actors and server timestamps;
- Collect audit trails and version-linked change reasons where available;
- a deterministic project checkpoint and timestamped run manifest.
- a separate daily project user-and-role snapshot, subject to the regular
  account's Central permissions;
- an automated validation certificate containing the run's reconciliation,
  identity, chain and timestamp checks.

The server-wide Central audit feed is deliberately opt-in. Set
`server_audit_enabled` to `true` only when forensic lifecycle events such as
form deletion, submission purge, password changes or logins are required and
the account has Server Administrator permission. It is not needed for the
basic MHRA-proportionate source-integrity workflow. Central does not generally
emit ordinary web logout events.

When enabled, the first lifecycle backfill can be bounded with
`server_audit_start`. Later runs use the latest audit-form submission time as
the next cursor, with a small overlap. If disabled, no server-wide audit call
is made.

## Privileged monthly administration snapshot

Run the separate administrator review explicitly:

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --admin-validate
```

Configure `admin_email`, `admin_project_ids`, optional `admin_audit_start` and
`admin_audit_end`, and optional `admin_host_snapshot_path`. The admin password
is prompted for interactively. A blank window covers the preceding 31 days.
The run submits one `admin_platform_snapshot` record containing the scoped
Central administration evidence and JSON/PDF/ZIP outputs. Host disk space and
uptime are not exposed by the ordinary Central API; supply them through the
optional host snapshot JSON when required. See
`docs/operational/ADMIN_SENTINEL.md`.

## Evidence and storage boundary

The exact source bytes are hashed in memory. The audit form stores hashes,
identifiers and references, not a second copy of participant data. Each run
creates a manifest; when RFC3161 is available, the manifest hash is submitted
to the configured TSA and the manifest, token and certificate are attached to
the audit record. Each manifest also carries the previous manifest's audit
record ID and hash, creating a timestamped run-level chain. Sentinel verifies
the previous manifest attachment when it can and reports a missing or changed
link. If the TSA is unavailable, the manifest is retained with an explicit
non-timestamped status. Sentinel does not use a per-source-record
`previous_attestation_hash` chain.

Completed records are not rewritten. A subsequent run skips an existing
deterministic record and only submits new source versions or new enabled audit
events.

Each run submits one consolidated `run_timestamp_manifest` record carrying the
timestamp manifest, project health snapshot, project user/role snapshot,
validation report/certificate and any evidence package through their dedicated
attachment fields. This keeps the audit table at one run line while preserving
separate downloadable evidence files. The JSON/PDF files capture
project-account-visible Central observations such as project metadata,
source-form inventory, user assignments, form version counts, submission
counts, retained-version counts and latest submission times. Host-wide metrics
such as disk space, uptime, CPU, memory and backups require separately
privileged Admin Sentinel.

## Failure and recovery behavior

Sentinel is designed to degrade safely. With the default preferred timestamp
policy, an unavailable RFC3161 service preserves the manifest and marks it
explicitly as not timestamped; it does not discard the source audit. A missing
or changed previous manifest is recorded as a chain warning while source
archiving may continue. If a run stops part-way through, rerunning it skips
deterministic records already accepted by Central and resumes the remainder.

Central outages or insufficient permissions can stop a run, but Sentinel does
not edit or delete source data. Set `timestamp_policy` to `required` only when
the run must fail unless a trusted timestamp is obtained.

The prior Sentinel pilot and MethodMesh recipe/reconstruction work has been
preserved in Git stash `pre-archival-sentinel-baseline-2026-10-05` and is not
part of this current baseline.

This is an engineering pilot, not a validated production clinical-trial
system.

## Automated validation outputs

Run the read-only validation review with:

```text
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate
```

Install the project dependencies once in the same Python environment used to
run Sentinel so the PDF certificate can be generated:

```text
python3 -m pip install -e .
```

By default this writes paired artifacts under
`.sentinel-local/validation/`:

- `validation_report.json` - the machine-readable authoritative report;
- `validation_certificate.pdf` - the human-readable certificate, with one row
  per test, component ownership, mode, pass/fail result and a link to the JSON
  evidence bundle.
- `evidence_package.zip` - the active-validation bundle containing raw API
  evidence and an SHA-256 manifest.

The PDF is a review view, not a replacement for the JSON. Central checks state
what the configured Central account could observe or read; Sentinel checks
state what Sentinel itself verified. The certificate does not silently claim
validation of Collect, Enketo, MethodMesh or host infrastructure unless those
tests are explicitly present and evidenced.

### Active synthetic validation

Once the project validation forms are published and listed in
`validation_form_ids`, run the Central/Sentinel exercise with:

```text
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate-active
```

This creates one synthetic record in `sentinel_validation_central`, updates it
once, and runs a 20-check Central/Sentinel exercise covering form-definition
readability, creation, retained structured versions, distinct version
identities, independent original-version readback, attachment inventory,
field-level diff, linked reason, audit-trail and actor evidence, metadata and
comments access, XML well-formedness, validation-run identity, before/after
hashes, deterministic identity, evidence capture and synthetic-form scope.
The JSON report and PDF certificate are written to the same validation output
directory as the read-only review.

The active report is also submitted to the configured audit form as a
`validation_certificate` record, with `validation_report.json`, the PDF when
available, and `evidence_package.zip` attached. The command prints the
resulting audit record ID.

Each certificate row's `evidence_ref` points to a concrete member of the ZIP,
not to the summary JSON. The package includes the original and edited XML,
retained-version metadata, Central diffs, audit events, actor metadata,
comments, attachment inventory, form definition and Sentinel scope/plan
evidence. `evidence_manifest.json` records the SHA-256 and size of every
packaged file. When selecting the original Central version, Sentinel uses the
retained version whose `instanceId` matches the original logical submission;
it does not assume Central returns versions in chronological order.

The active run uses synthetic validation data only. It does not open, edit or
delete a source-study submission, and it does not claim to have tested
Collect, Enketo or MethodMesh. Those components require their separate
fixtures and, where necessary, a device or browser witness. The underlying
calls use the [ODK Central submission API](https://docs.getodk.org/central-api-submission-management/)
and its [OpenRosa endpoints](https://docs.getodk.org/central-api-openrosa-endpoints/).
