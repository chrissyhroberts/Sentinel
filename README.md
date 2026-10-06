# Sentinel
# MethodMesh Governance Sentinel

Sentinel is an integrity ledger and project audit service for ODK Central. It
records hashes and references for source-form versions, original submissions,
retained Central edits, change reasons and timestamp evidence. The source data
remains in ODK Central; Sentinel does not copy it into a second form. It does
not reconstruct canonical MethodMesh payloads from XLSForm recipes.

See [the archival baseline](docs/ARCHIVAL_BASELINE.md) for the governing
scope, evidence model and archive layout.

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
the [universal project audit form contract](docs/PROJECT_AUDIT_FORM_CONTRACT.md).

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
the audit record. If the TSA is unavailable, the manifest is retained with an
explicit non-timestamped status. Sentinel does not backdate timestamps or use
`previous_attestation_hash` as a chain of trust.

Completed records are not rewritten. A subsequent run skips an existing
deterministic record and only submits new source versions or new enabled audit
events.

The prior Sentinel pilot and MethodMesh recipe/reconstruction work has been
preserved in Git stash `pre-archival-sentinel-baseline-2026-10-05` and is not
part of this current baseline.

This is an engineering pilot, not a validated production clinical-trial
system.
