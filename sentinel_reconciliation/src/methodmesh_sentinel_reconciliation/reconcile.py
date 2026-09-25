from __future__ import annotations

import base64
import csv
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

STATUS_RECOGNISED = "recognised"
STATUS_UNKNOWN_ISSUER = "unknown_issuer"
STATUS_UNKNOWN_CREDENTIAL = "unknown_credential"
STATUS_ISSUER_MISMATCH = "issuer_mismatch"
STATUS_REVOKED = "revoked"
STATUS_INVALID_EVIDENCE = "invalid_evidence"

RECONCILIATION_SCHEMA = "methodmesh.sentinel.credential_reconciliation.v1"
VERIFICATION_EVIDENCE_FORMAT = "methodmesh_nfc_credential_verification_v1"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _bool(value: Any) -> bool | None:
    text = _clean(value).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _iso(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def _field(row: Mapping[str, Any], name: str) -> str:
    if name in row:
        return _clean(row[name])
    suffixes = (f"-{name}", f"/{name}", f".{name}")
    hits = [k for k in row if k.endswith(suffixes)]
    if len(hits) == 1:
        return _clean(row[hits[0]])
    if len(hits) > 1:
        nonblank = [(k, _clean(row[k])) for k in hits if _clean(row[k])]
        if len(nonblank) == 1:
            return nonblank[0][1]
        if nonblank:
            raise ValueError(f"Ambiguous ODK field {name}: {[k for k, _ in nonblank]}")
    return ""


def _json_field(row: Mapping[str, Any], name: str) -> dict[str, Any]:
    text = _field(row, name)
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {"__parse_error__": True}
    return value if isinstance(value, dict) else {"__parse_error__": True}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_verification_evidence_hash(row: Mapping[str, Any]) -> str:
    uid = _field(row, "mm_auth_tag_uid_hex").replace(" ", "").upper()
    credential_id = _field(row, "mm_auth_credential_id")
    subject_id = _field(row, "mm_auth_credential_subject_id")
    envelope_hash = _field(row, "mm_auth_credential_envelope_hash").lower()
    issuer_fp = _field(row, "mm_auth_issuer_public_key_fingerprint_sha256").lower()
    issuer_signature_valid = _bool(_field(row, "mm_auth_issuer_signature_valid"))
    pin_verified = _bool(_field(row, "mm_auth_pin_verified"))
    if not all([uid, credential_id, subject_id, envelope_hash, issuer_fp]):
        return ""
    if issuer_signature_valid is None or pin_verified is None:
        return ""
    canonical = "\n".join([
        f"verification_evidence_format={VERIFICATION_EVIDENCE_FORMAT}",
        f"tag_uid_hex={uid}",
        f"credential_id={credential_id}",
        f"credential_subject_id={subject_id}",
        f"credential_envelope_hash={envelope_hash}",
        f"issuer_public_key_fingerprint_sha256={issuer_fp}",
        f"issuer_signature_valid={'true' if issuer_signature_valid else 'false'}",
        f"pin_verified={'true' if pin_verified else 'false'}",
    ])
    return sha256_text(canonical)


def _public_key_fingerprint(public_key_base64: str) -> str:
    try:
        raw = base64.b64decode(public_key_base64, validate=True)
    except Exception:
        return ""
    return hashlib.sha256(raw).hexdigest()


def _event_time(row: Mapping[str, Any], att: Mapping[str, Any]) -> tuple[datetime | None, str]:
    if _clean(att.get("trusted_timestamp_status")) == "rfc3161_verified":
        dt = _iso(att.get("trusted_timestamp_time_iso"))
        if dt:
            return dt, "attestation.trusted_timestamp_time_iso"
    dt = _iso(_field(row, "mm_auth_credential_verified_time_iso"))
    if dt:
        return dt, "credential_verified_time_iso"
    for candidate in ("SubmissionDate", "submission_date", "end", "start"):
        dt = _iso(_field(row, candidate))
        if dt:
            return dt, candidate
    return None, "unavailable"


def _active_at(record: Mapping[str, Any] | None, event_time: datetime | None) -> bool | None:
    if record is None:
        return None
    status = _clean(record.get("status")).lower()
    start = _iso(record.get("valid_from_iso") or record.get("commissioned_at_iso"))
    end = _iso(record.get("valid_until_iso") or record.get("retired_at_iso"))
    revoked = _iso(record.get("revoked_at_iso"))
    if event_time is None:
        if status in {"revoked", "retired", "inactive", "superseded"}:
            return False
        if status in {"active", "approved", "issued"}:
            return True
        return None
    if start and event_time < start:
        return False
    if revoked and event_time >= revoked:
        return False
    if end and event_time > end:
        return False
    if status == "revoked" and not revoked:
        return False
    if status in {"inactive", "superseded"} and not end:
        return False
    return True


def _load_registry(path: str | Path, key: str) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = _clean(row.get(key))
        if not value:
            continue
        normalized = value.lower() if "fingerprint" in key else value
        if normalized in result:
            raise ValueError(f"Duplicate registry key {key}={value}")
        result[normalized] = {k: _clean(v) for k, v in row.items()}
    return result


@dataclass(frozen=True)
class ReconciliationResult:
    schema: str
    submission_key: str
    study_id: str
    form_id: str
    form_version: str
    credential_id: str
    credential_subject_id: str
    issuer_public_key_fingerprint_sha256: str
    issuer_key_id: str
    event_time_iso: str
    event_time_basis: str
    credential_crypto_valid: bool
    evidence_consistency_valid: bool
    issuer_registered: bool
    issuer_active_at_event: bool | None
    credential_registered: bool
    credential_subject_match: bool | None
    credential_issuer_match: bool | None
    credential_active_at_event: bool | None
    attestation_binding_valid: bool
    verification_evidence_hash_valid: bool
    issuer_public_key_fingerprint_valid: bool
    credential_signature_reverification: str
    study_credential_status: str
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile_submission(
    row: Mapping[str, Any],
    provisioning_devices: Mapping[str, Mapping[str, Any]],
    issued_credentials: Mapping[str, Mapping[str, Any]],
) -> ReconciliationResult:
    reasons: list[str] = []
    issuer_fp = _field(row, "mm_auth_issuer_public_key_fingerprint_sha256").lower()
    issuer_key_id = _field(row, "mm_auth_issuer_key_id").lower()
    credential_id = _field(row, "mm_auth_credential_id")
    subject_id = _field(row, "mm_auth_credential_subject_id")
    study_id = _field(row, "mm_study_id")
    form_id = _field(row, "mm_form_id")
    form_version = _field(row, "mm_form_version")
    submission_key = _field(row, "KEY") or _field(row, "meta-instanceID") or _field(row, "mm_workflow_instance_id")

    credential_crypto_valid = all([
        _bool(_field(row, "mm_auth_credential_verified")) is True,
        _bool(_field(row, "mm_auth_pin_verified")) is True,
        _bool(_field(row, "mm_auth_issuer_signature_valid")) is True,
    ])
    if not credential_crypto_valid:
        reasons.append("MethodMesh credential/PIN/signature success evidence is not all true.")

    supplied_evidence_hash = _field(row, "mm_auth_verification_evidence_hash").lower()
    recomputed_evidence_hash = canonical_verification_evidence_hash(row)
    verification_evidence_hash_valid = bool(
        supplied_evidence_hash and recomputed_evidence_hash and supplied_evidence_hash == recomputed_evidence_hash
    )
    if not verification_evidence_hash_valid:
        reasons.append("NFC verification evidence hash does not reconstruct from submitted fields.")

    public_key_base64 = _field(row, "mm_auth_issuer_public_key_base64")
    derived_fp = _public_key_fingerprint(public_key_base64)
    issuer_public_key_fingerprint_valid = bool(
        issuer_fp and derived_fp and issuer_fp == derived_fp and issuer_key_id == issuer_fp[:16]
    )
    if not issuer_public_key_fingerprint_valid:
        reasons.append("Issuer public key does not reconstruct the submitted canonical fingerprint/key ID.")

    auth = _json_field(row, "mm_auth_methodmesh_full_json")
    att = _json_field(row, "mm_att_methodmesh_full_json")
    auth_execution_id = _field(row, "mm_auth_methodmesh_execution_id")
    att_event_hash = _field(row, "mm_att_event_payload_hash").lower()
    event_hash = _field(row, "mm_event_payload_hash").lower()
    frozen = _field(row, "mm_frozen_canonical_commitment")
    frozen_hash_valid = bool(frozen and event_hash and sha256_text(frozen) == event_hash)
    if not frozen_hash_valid:
        reasons.append("Frozen canonical ODK commitment does not hash to mm_event_payload_hash.")

    source = (
        att.get("execution_provenance", {})
        .get("actors", {})
        .get("operator", {})
        .get("assertion_evidence", {})
        if isinstance(att, dict)
        else {}
    )
    attestation_binding_checks = [
        bool(att) and not att.get("__parse_error__"),
        _clean(att.get("methodmesh_method_id")) == "attestation.create",
        _clean(att.get("methodmesh_status")) == "Succeeded",
        _clean(att.get("event_payload_hash")).lower() == event_hash,
        att_event_hash == event_hash,
        _clean(source.get("source_execution_id")) == auth_execution_id,
        _clean(source.get("source_verification_evidence_hash")).lower() == supplied_evidence_hash,
        _clean(source.get("issuer_public_key_fingerprint_sha256")).lower() == issuer_fp,
        _clean(att.get("operator_id")) == subject_id,
        _bool(_field(row, "mm_attested_hash_matches_odk_hash")) is True,
        _bool(_field(row, "mm_ready_to_submit")) is True,
        frozen_hash_valid,
    ]
    attestation_binding_valid = all(attestation_binding_checks)
    if not attestation_binding_valid:
        reasons.append("Submitted attestation does not consistently bind the authentication execution to the frozen ODK commitment.")

    auth_consistency_checks = [
        bool(auth) and not auth.get("__parse_error__"),
        _clean(auth.get("methodmesh_method_id")) == "nfc_credential_verification",
        _clean(auth.get("methodmesh_status")) == "Succeeded",
        _clean(auth.get("methodmesh_execution_id")) == auth_execution_id,
        _clean(auth.get("credential_id")) == credential_id,
        _clean(auth.get("credential_subject_id")) == subject_id,
        _clean(auth.get("issuer_public_key_fingerprint_sha256")).lower() == issuer_fp,
        _clean(auth.get("verification_evidence_hash")).lower() == supplied_evidence_hash,
    ]
    if not all(auth_consistency_checks):
        reasons.append("Flat authentication fields do not match the immutable MethodMesh authentication envelope.")

    evidence_consistency_valid = all([
        credential_crypto_valid,
        verification_evidence_hash_valid,
        issuer_public_key_fingerprint_valid,
        attestation_binding_valid,
        all(auth_consistency_checks),
    ])

    event_time, event_basis = _event_time(row, att)
    event_time_iso = event_time.isoformat().replace("+00:00", "Z") if event_time else ""

    issuer_record = provisioning_devices.get(issuer_fp)
    issuer_registered = issuer_record is not None
    issuer_active = _active_at(issuer_record, event_time)
    if not issuer_registered:
        reasons.append("Issuer fingerprint is not present in the provisioning-device registry.")
    elif issuer_active is False:
        reasons.append("Provisioning-device issuer was not active at the event time.")

    credential_record = issued_credentials.get(credential_id)
    credential_registered = credential_record is not None
    credential_subject_match: bool | None = None
    credential_issuer_match: bool | None = None
    credential_active: bool | None = None
    if not credential_registered:
        reasons.append("Credential ID is not present in the issued-credential registry.")
    else:
        expected_subject = _clean(credential_record.get("credential_subject_id"))
        credential_subject_match = (not expected_subject) or expected_subject == subject_id
        expected_issuer = _clean(credential_record.get("issuer_public_key_fingerprint_sha256")).lower()
        credential_issuer_match = bool(expected_issuer) and expected_issuer == issuer_fp
        credential_active = _active_at(credential_record, event_time)
        if not credential_subject_match:
            reasons.append("Credential subject does not match the issued-credential registry.")
        if not credential_issuer_match:
            reasons.append("Credential is registered to a different issuer fingerprint.")
        if credential_active is False:
            reasons.append("Credential was not active at the event time.")

    if not evidence_consistency_valid or credential_subject_match is False:
        status = STATUS_INVALID_EVIDENCE
    elif not issuer_registered:
        status = STATUS_UNKNOWN_ISSUER
    elif not credential_registered:
        status = STATUS_UNKNOWN_CREDENTIAL
    elif credential_issuer_match is False:
        status = STATUS_ISSUER_MISMATCH
    elif issuer_active is False or credential_active is False:
        status = STATUS_REVOKED
    else:
        status = STATUS_RECOGNISED

    # ROSC1 submissions expose the issuer public key and MethodMesh's verification
    # result, but not the signed credential envelope/signature bytes needed to
    # independently replay the original ECDSA verification in Sentinel.
    credential_signature_reverification = "not_available_from_rosc1_submission_v1"

    return ReconciliationResult(
        schema=RECONCILIATION_SCHEMA,
        submission_key=submission_key,
        study_id=study_id,
        form_id=form_id,
        form_version=form_version,
        credential_id=credential_id,
        credential_subject_id=subject_id,
        issuer_public_key_fingerprint_sha256=issuer_fp,
        issuer_key_id=issuer_key_id,
        event_time_iso=event_time_iso,
        event_time_basis=event_basis,
        credential_crypto_valid=credential_crypto_valid,
        evidence_consistency_valid=evidence_consistency_valid,
        issuer_registered=issuer_registered,
        issuer_active_at_event=issuer_active,
        credential_registered=credential_registered,
        credential_subject_match=credential_subject_match,
        credential_issuer_match=credential_issuer_match,
        credential_active_at_event=credential_active,
        attestation_binding_valid=attestation_binding_valid,
        verification_evidence_hash_valid=verification_evidence_hash_valid,
        issuer_public_key_fingerprint_valid=issuer_public_key_fingerprint_valid,
        credential_signature_reverification=credential_signature_reverification,
        study_credential_status=status,
        reasons=reasons,
    )


def reconcile_csv(
    submissions_csv: str | Path,
    provisioning_devices_csv: str | Path,
    issued_credentials_csv: str | Path,
) -> list[ReconciliationResult]:
    issuers = _load_registry(provisioning_devices_csv, "issuer_public_key_fingerprint_sha256")
    credentials = _load_registry(issued_credentials_csv, "credential_id")
    with Path(submissions_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return [reconcile_submission(row, issuers, credentials) for row in rows]


def write_csv(results: Iterable[ReconciliationResult], path: str | Path) -> None:
    rows = [r.as_dict() for r in results]
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    flattened = []
    for row in rows:
        row = dict(row)
        row["reasons"] = " | ".join(row["reasons"])
        flattened.append(row)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flattened[0].keys()))
        writer.writeheader()
        writer.writerows(flattened)


def write_jsonl(results: Iterable[ReconciliationResult], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")) + "\n")
