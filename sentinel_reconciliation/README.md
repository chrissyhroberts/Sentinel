# Sentinel credential reconciliation engine — v0.1.0

This is the first bounded implementation of the MethodMesh Sentinel central credential-reconciliation layer.
It is deliberately a **deterministic task engine**, not a new clinical database and not a runtime dependency for MethodMesh.

## What it does

For each ODK submission produced by the evidence-first MethodMesh compiler it:

1. reconstructs the `methodmesh_nfc_credential_verification_v1` evidence hash from the submitted fields;
2. recomputes the issuer public-key SHA-256 fingerprint from the submitted DER/X.509 public key bytes;
3. checks that the short issuer key ID is the first 16 hex characters of the full fingerprint;
4. parses the immutable MethodMesh authentication and attestation envelopes;
5. checks that the attestation binds the same authentication execution, issuer fingerprint and source verification-evidence hash;
6. recomputes SHA-256 over the frozen ODK canonical commitment and compares it with the ODK/attestation payload hash;
7. chooses an event time, preferring a verified RFC 3161 attestation timestamp where present;
8. reconciles the observed issuer against the provisioning-device registry;
9. reconciles the credential ID, subject, expected issuer and event-time validity against the issued-credential registry;
10. emits a derived status and an append-oriented JSONL reconciliation event.

Final `study_credential_status` is one of:

- `recognised`
- `unknown_issuer`
- `unknown_credential`
- `issuer_mismatch`
- `revoked`
- `invalid_evidence`

The classification is deterministic. It does not rewrite the source ODK submission or either registry.

## Important assurance boundary

ROSC1 v1 submissions currently contain MethodMesh's `issuer_signature_valid=true` result, the issuer public key, credential/envelope hashes and the evidence binding, but they **do not contain the original signed credential envelope/signature material needed for Sentinel to replay the credential's ECDSA issuer-signature verification independently**.

For that reason this engine records:

```text
credential_signature_reverification = not_available_from_rosc1_submission_v1
```

It does **not** silently claim independent replay of that signature. This is a remaining evidence-contract gap for a later bounded unit. The engine does independently verify the evidence relations that are reconstructable from the current submitted record.

## Registry schemas

`provisioning_devices.csv` key:

```text
issuer_public_key_fingerprint_sha256
```

The full 64-character fingerprint is authoritative. `issuer_key_id` is descriptive/backwards-compatible only.

`issued_credentials.csv` key:

```text
credential_id
```

Each credential row links to its expected full issuer fingerprint and may define validity/revocation times.

Templates are in `examples/`.

## Install and run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .

.venv/bin/sentinel-reconcile-credentials \
  --submissions submissions.csv \
  --provisioning-devices provisioning_devices.csv \
  --issued-credentials issued_credentials.csv \
  --out reconciliation.csv \
  --events-jsonl reconciliation_events.jsonl
```

The registry CSVs are pilot interchange formats. In the full Sentinel product the governed source should be the Sidecar-derived registry state rather than a manually maintained spreadsheet.
