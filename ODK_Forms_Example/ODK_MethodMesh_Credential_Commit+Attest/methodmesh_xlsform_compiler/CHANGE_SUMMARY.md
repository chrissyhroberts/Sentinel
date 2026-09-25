# MethodMesh XLSForm Compiler v0.3.0 — change summary

This release is the first compiler revision structured as a MethodMesh Sentinel task.

## Provenance-envelope corrections

- Generated MethodMesh calls now send the global v3 context fields the compiler genuinely knows: `study_id`, `form_id`, `form_version`, and `form_instance_id`.
- The compiler-generated workflow UUID is now correctly mapped to `form_instance_id`.
- The previous incorrect mapping of that UUID to `visit_id` has been removed.
- `visit_id` and `event_id` are deliberately omitted until an explicit study mapping exists.
- `attestation.create` continues to pass the NFC credential subject as `operator_id` and the earlier NFC execution as `input_verification_execution_id`; MethodMesh can therefore retain the distinction between caller-declared operator context and the stronger verification evidence.

## Release identity

- Compiler-owned ODK versions now use `YYYYMMDDHHMMSS`, avoiding collisions when multiple legitimate releases are compiled in one minute.
- The same generated version is written to `settings.version`, `mm_form_version`, filenames and release manifests.

## Sentinel task foundation

- Added generic task-event schema `methodmesh.sentinel.task_event.v1`.
- Added task type `form.compile`, schema version `1`.
- Added `run_form_compile_task()` as the orchestration entry point used by the CLI.
- Kept `compile_xlsform()` as the deterministic transformation primitive beneath the task layer.
- Successful builds emit `sentinel_task_event.json` containing request ID, request source, optional operator context, source hash, parameters, start/completion time, monotonic duration, compiler version/fingerprint, result status, warnings and output artifact hashes.
- Failed task executions emit a failure event beneath `_sentinel_failed_tasks/` before the compiler error is re-raised.
- `commitment_manifest.json` links the release to its Sentinel request/event.
- `CHECKSUMS.sha256` covers the Sentinel task receipt as part of the release bundle.

This deliberately does **not** implement the Sentinel VM/API, ODK sidecar posting or desktop GUI yet. Those future surfaces should call the same task contract rather than duplicate compiler logic.

## Verification performed

- 16 unit/regression tests pass.
- Example XLSForm compiled through the CLI successfully.
- Generated NFC and attestation intents contain the new v3 context and no fake `visit_id`.
- Release checksum verification passes, including `sentinel_task_event.json`.
- Failure-path task receipt tested.
