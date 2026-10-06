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

The directory is gitignored. Passwords are entered interactively and are not
saved by Sentinel.

The audit boundary is always one explicitly configured Central project. See
the [universal project audit form contract](docs/operational/PROJECT_AUDIT_FORM_CONTRACT.md).

Operational procedures are in [docs/operational](docs/operational/). The
risk-based validation checklist and workflow are in
[docs/validation](docs/validation/).

The current test form is `audit_001`, version 2. The form ID and version are
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

Each run also submits a `validation_certificate` record. Its JSON attachment
contains the automated check results and is independently timestamped using
the same preferred/required policy. A certificate with warnings is still
preserved for review; a required timestamp failure stops the run.

Each run also submits a `project_health_snapshot` record with a
`platform_snapshot.json` attachment. It captures project-account-visible
Central observations such as project metadata, source-form inventory, form
version counts, submission counts, retained-version counts and latest
submission times. It deliberately excludes host-wide metrics such as disk
space, uptime, CPU, memory and backups; those require a separately privileged
Admin Sentinel.

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

By default this writes two paired artifacts under
`.sentinel-local/validation/`:

- `validation_report.json` - the machine-readable authoritative report;
- `validation_certificate.pdf` - the human-readable certificate, with one row
  per test, component ownership, mode, pass/fail result and a link to the JSON
  evidence bundle.

The PDF is a review view, not a replacement for the JSON. Central checks state
what the configured Central account could observe or read; Sentinel checks
state what Sentinel itself verified. The certificate does not silently claim
validation of Collect, Enketo, MethodMesh or host infrastructure unless those
tests are explicitly present and evidenced.
