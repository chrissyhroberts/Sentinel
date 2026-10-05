# Sentinel archival baseline

This is the current Sentinel design. It intentionally starts with a small,
auditable responsibility rather than attempting to reconstruct a canonical
MethodMesh payload from every XLSForm.

## Responsibility

For every retained ODK Central version of a logical submission, Sentinel:

1. downloads the exact Central submission bytes;
2. downloads the exact ODK Collect audit trail when present;
3. downloads the exact attachments;
4. records the Central version, actor, time, audit events and change reasons;
5. hashes every archived file independently;
6. requests or records trusted timestamp evidence for the archived version;
7. writes a readable, consolidated audit record for the complete version history.

The archive is byte-preserving. Sentinel does not parse and reserialize the
submission, apply an XLSForm commitment recipe, reconstruct a canonical
payload, or use `previous_attestation_hash` as a chain of trust.

## Evidence layers

ODK Collect's audit trail describes activity on the device during form entry.
Central's retained versions and change-tracking events describe what happened
to the record after submission. Sentinel keeps both. A reason is reported as
confirmed only when it is supplied by Central's own change/audit event; a
comment without a native version link remains explicitly unlinked.

The RFC3161 timestamp establishes that the exact archived bytes existed no
later than the trusted timestamp. It does not backdate the event or prove that
the Collect wall-clock timestamp was accurate. When RFC3161 is unavailable,
Sentinel records the pending state together with local clock-drift and
monotonic evidence, then adds the later trusted timestamp when connectivity
returns.

## Central storage boundary

The production destination is the universal audit form published in the same
Central project. Sentinel may use bounded transient files while downloading or
building one source bundle, but it must not retain a local research archive.
The local `ArchiveStore` implementation is currently a deterministic test
harness for the record structure; the Central-backed sink is the required
production path.

The Central audit record contains one exact source bundle attachment when the
retention policy requires it. That bundle contains the original submission,
Collect audit file, and attachments. The audit form therefore becomes the
durable archive without introducing a second database or a project-specific
Sentinel installation.

## Development fixture layout

```text
archive/
  forms/<form>/instances/<instance>/
    audit_record.json
    audit_record.html
    versions/<central-version>/
      submission.xml
      audit.csv
      attachments/*
      version_manifest.json
```

The fixture layout is for local tests only. In production, the same manifest
and report are submitted to the project audit form and the exact source bundle
is retained there.

## XLSForm boundary

The XLSForm may use MethodMesh NFC verification to identify the operator and
may enable the normal ODK Collect audit trail. It does not need to construct a
canonical hash recipe or call `attestation.create` for ordinary submissions.
Sentinel performs the archival hash and timestamp operation after Central
receipt.

## Scope deliberately deferred

- independent replay of MethodMesh signatures;
- canonical recipe reconstruction;
- semantic field-level reconstruction from arbitrary XML versions;
- automatic inference of a reason from timestamp proximity;
- claiming that a later RFC3161 token backdates source creation;
- treating a linked-hash chain as the primary evidence model.

These can be added later without changing the byte-preserving archive.
