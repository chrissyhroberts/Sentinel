# Sentinel
# MethodMesh Governance Sentinel

Sentinel is currently an integrity-ledger and audit service for ODK Central
trial data. It records hashes and references for the exact original
submission, every retained Central edit, Central change reasons and timestamp
evidence. The source data remains in ODK Central; Sentinel does not copy it
into a second form. The current baseline deliberately does not reconstruct
canonical MethodMesh payloads from XLSForm recipes.

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

The small reference implementation is in `sentinel_archive/`. It is designed
to be called by the future Central downloader: give it the exact downloaded
submission, audit file, attachments, Central metadata, change events and any
timestamp receipt, and it writes an immutable per-version archive plus a
human-readable audit record.

The prior Sentinel pilot and MethodMesh recipe/reconstruction work has been
preserved in Git stash `pre-archival-sentinel-baseline-2026-10-05` and is not
part of this current baseline.

This is an engineering pilot, not a validated production clinical-trial
system.
