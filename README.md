# Sentinel
# MethodMesh Governance Sentinel

Sentinel is currently an archival and audit service for ODK Central trial data.
It preserves the exact original submission, the ODK Collect audit trail, every
retained Central edit, attachments, Central change reasons and timestamp
evidence. The current baseline deliberately does not reconstruct canonical
MethodMesh payloads from XLSForm recipes.

See [the archival baseline](docs/ARCHIVAL_BASELINE.md) for the governing
scope, evidence model and archive layout.

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
