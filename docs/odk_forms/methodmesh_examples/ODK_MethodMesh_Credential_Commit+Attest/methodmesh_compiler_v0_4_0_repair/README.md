# MethodMesh XLSForm compiler v0.4.0 repair

Baseline: the attached Sentinel v0.3.0 compiler/task implementation.

Adds:
- evidence-first NFC authentication;
- full issuer fingerprint + verification evidence binding;
- central reconciliation semantics;
- ODK-compatible label + hint on every generated `mm_auth_*` and `mm_att_*` return field;
- preserves the v0.3 Sentinel `form.compile` task receipt and immutable release-bundle design.

The apply script replaces compiler implementation/tests/docs only. It deliberately preserves `.venv`, `examples/`, `methodmesh_build/`, and any generated release bundles in the target directory.
