# Changelog

## 0.2.0 — 2026-10-07

This release establishes the current Sentinel archival and QA baseline.

- archives every retained Central submission version with deterministic IDs,
  hashes, edit diffs, actors and linked change reasons;
- consolidates run-level QA evidence into a single Sentinel audit row with
  timestamp manifest, project health, user/role, validation and evidence-pack
  attachments;
- adds human-readable QA, governance and validation PDFs alongside the
  authoritative JSON and raw evidence files;
- adds active synthetic validation for Central submission edits, reasons,
  attachments, audit evidence and disposable form create/delete/Trash
  lifecycle checks;
- records the exact deployed source-form XML and, when available, the original
  XLSForm workbook on each form-version audit record;
- keeps server-wide Central audit collection explicitly optional, so the
  regular account can run a proportionate project-scoped audit;
- documents the Central API coverage, project audit-form contract, validation
  workflow and current ALCOA+ boundary.

This remains an engineering pilot and requires project-specific validation,
SOPs, access-control review and operational qualification before use as a
validated clinical-trial system.
