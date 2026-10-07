# Changelog

## 0.3.0 — Sentinel task foundation

- Added `methodmesh.sentinel.task_event.v1` and task type `form.compile`.
- CLI now invokes `run_form_compile_task()`; core XLSForm transformation remains in `compile_xlsform()`.
- Added `sentinel_task_event.json` to successful release bundles and failed task receipts under `_sentinel_failed_tasks/`.
- Added request IDs, execution timing, compiler implementation identity, source hash, output artifact hashes, warnings and status to task receipts.
- Added task linkage to `commitment_manifest.json` and checksum coverage of the task receipt.
- Corrected MethodMesh envelope context: workflow UUID is now `form_instance_id`, not `visit_id`; generated calls also carry `study_id`, `form_id` and `form_version`.
- Preserved NFC operator linkage on `attestation.create` through `operator_id` and `input_verification_execution_id`.
- Changed compiler-owned release versions from minute to second resolution (`YYYYMMDDHHMMSS`).
- Updated tests and documentation.

## 0.2.0

- Immutable release bundles, preserved source, manifests, implementation fingerprint and checksum inventory.
