# Component validation checklist set

The validation set is deliberately split by component. Each item records its
execution mode:

- **Automated:** Sentinel or a dedicated harness produces the evidence.
- **Hybrid:** an automated action produces evidence and a person reviews it.
- **Witnessed:** a person must observe a device or user-interface behavior.

The first automated entry point is:

```text
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate
```

It is read-only. It produces a JSON validation report covering the configured
Central project and Sentinel configuration; it does not submit or edit data.
It also writes a paired `validation_certificate.pdf` for human review. The
JSON remains authoritative and the PDF links each row back to that report.

For an active, synthetic Central/Sentinel test, run:

```text
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --validate-active
```

This uses only `sentinel_validation_central`. It creates one test submission,
performs one controlled edit, and verifies the retained versions, Central
diff/reason evidence and before/after XML hashes. It is safe to repeat because
each run uses a fresh validation run ID. It is not a substitute for the
Collect, Enketo or MethodMesh checks below.

Detailed checklists:

- [ODK Central](ODK_CENTRAL_VALIDATION_CHECKLIST.md)
- [ODK Collect](ODK_COLLECT_VALIDATION_CHECKLIST.md)
- [Enketo](ENKETO_VALIDATION_CHECKLIST.md)
- [MethodMesh](METHODMESH_VALIDATION_CHECKLIST.md)
- [Sentinel](SENTINEL_VALIDATION_CHECKLIST.md)

The ODK Central checklist is intentionally broader than Sentinel's own
validation. It tests the Central project/API surface visible to the configured
account: project metadata, form inventory, published definitions, source
submissions and retained versions, audit-form access, permissions and Central
edit/reason behavior. It does not certify Sentinel's hashing, manifest chain,
timestamp handling or recovery logic.

The Sentinel checklist tests Sentinel-specific behavior against that Central
surface. It does not certify Central's server, database, backups, host uptime,
browser rendering, device behavior or MethodMesh implementation.

The Collect, Enketo and MethodMesh checklists cover the upstream components and
identify where an automated fixture or device/browser harness can replace a
manual step. A passing Central or Sentinel report must not be treated as a
passing result for those components.

The completed report, test inputs, logs, hashes and any witnessed evidence are
retained together as the validation evidence for that release and review
period. No checklist item is considered validated merely because the code
contains a corresponding feature.
