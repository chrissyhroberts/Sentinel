import base64
import hashlib
import json
import unittest

from methodmesh_sentinel_reconciliation.reconcile import (
    canonical_verification_evidence_hash,
    reconcile_submission,
)


ISSUER_BYTES = b"synthetic issuer public key bytes"
ISSUER_B64 = base64.b64encode(ISSUER_BYTES).decode()
ISSUER_FP = hashlib.sha256(ISSUER_BYTES).hexdigest()
ISSUER_ID = ISSUER_FP[:16]


def make_row(issuer_fp=ISSUER_FP, issuer_id=ISSUER_ID, credential_id="cred_1", subject="STAFF-001"):
    row = {
        "KEY": "uuid:test",
        "mm_study_id": "STUDY",
        "mm_form_id": "form",
        "mm_form_version": "1",
        "mm_authenticate_operator-mm_auth_methodmesh_execution_id": "auth-1",
        "mm_authenticate_operator-mm_auth_credential_verified": "true",
        "mm_authenticate_operator-mm_auth_pin_verified": "true",
        "mm_authenticate_operator-mm_auth_issuer_signature_valid": "true",
        "mm_authenticate_operator-mm_auth_credential_id": credential_id,
        "mm_authenticate_operator-mm_auth_credential_subject_id": subject,
        "mm_authenticate_operator-mm_auth_credential_envelope_hash": "a" * 64,
        "mm_authenticate_operator-mm_auth_issuer_key_id": issuer_id,
        "mm_authenticate_operator-mm_auth_issuer_public_key_fingerprint_sha256": issuer_fp,
        "mm_authenticate_operator-mm_auth_issuer_public_key_base64": ISSUER_B64,
        "mm_authenticate_operator-mm_auth_tag_uid_hex": "04AABBCC",
        "mm_authenticate_operator-mm_auth_credential_verified_time_iso": "2026-09-25T12:00:00Z",
        "mm_frozen_canonical_commitment": "study_id=STUDY|form_id=form",
        "mm_attested_hash_matches_odk_hash": "true",
        "mm_ready_to_submit": "true",
    }
    row["mm_authenticate_operator-mm_auth_verification_evidence_hash"] = canonical_verification_evidence_hash(row)
    event_hash = hashlib.sha256(row["mm_frozen_canonical_commitment"].encode()).hexdigest()
    row["mm_event_payload_hash"] = event_hash
    row["mm_create_attestation-mm_att_event_payload_hash"] = event_hash
    auth = {
        "methodmesh_execution_id": "auth-1",
        "methodmesh_method_id": "nfc_credential_verification",
        "methodmesh_status": "Succeeded",
        "credential_id": credential_id,
        "credential_subject_id": subject,
        "issuer_public_key_fingerprint_sha256": issuer_fp,
        "verification_evidence_hash": row["mm_authenticate_operator-mm_auth_verification_evidence_hash"],
    }
    att = {
        "methodmesh_method_id": "attestation.create",
        "methodmesh_status": "Succeeded",
        "operator_id": subject,
        "event_payload_hash": event_hash,
        "trusted_timestamp_status": "rfc3161_verified",
        "trusted_timestamp_time_iso": "2026-09-25T12:01:00Z",
        "execution_provenance": {
            "actors": {
                "operator": {
                    "assertion_evidence": {
                        "source_execution_id": "auth-1",
                        "source_verification_evidence_hash": row["mm_authenticate_operator-mm_auth_verification_evidence_hash"],
                        "issuer_public_key_fingerprint_sha256": issuer_fp,
                    }
                }
            }
        },
    }
    row["mm_authenticate_operator-mm_auth_methodmesh_full_json"] = json.dumps(auth)
    row["mm_create_attestation-mm_att_methodmesh_full_json"] = json.dumps(att)
    return row


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.issuers = {
            ISSUER_FP: {
                "issuer_public_key_fingerprint_sha256": ISSUER_FP,
                "status": "active",
                "commissioned_at_iso": "2026-01-01T00:00:00Z",
            }
        }
        self.credentials = {
            "cred_1": {
                "credential_id": "cred_1",
                "credential_subject_id": "STAFF-001",
                "issuer_public_key_fingerprint_sha256": ISSUER_FP,
                "status": "active",
                "valid_from_iso": "2026-01-01T00:00:00Z",
            }
        }

    def test_recognised(self):
        result = reconcile_submission(make_row(), self.issuers, self.credentials)
        self.assertEqual(result.study_credential_status, "recognised")
        self.assertTrue(result.evidence_consistency_valid)
        self.assertTrue(result.attestation_binding_valid)

    def test_unknown_issuer_precedes_unknown_credential(self):
        other_bytes = b"other key"
        other_fp = hashlib.sha256(other_bytes).hexdigest()
        row = make_row(issuer_fp=other_fp, issuer_id=other_fp[:16], credential_id="other")
        row["mm_authenticate_operator-mm_auth_issuer_public_key_base64"] = base64.b64encode(other_bytes).decode()
        row["mm_authenticate_operator-mm_auth_verification_evidence_hash"] = canonical_verification_evidence_hash(row)
        auth = json.loads(row["mm_authenticate_operator-mm_auth_methodmesh_full_json"])
        auth["issuer_public_key_fingerprint_sha256"] = other_fp
        auth["verification_evidence_hash"] = row["mm_authenticate_operator-mm_auth_verification_evidence_hash"]
        auth["credential_id"] = "other"
        row["mm_authenticate_operator-mm_auth_methodmesh_full_json"] = json.dumps(auth)
        att = json.loads(row["mm_create_attestation-mm_att_methodmesh_full_json"])
        source = att["execution_provenance"]["actors"]["operator"]["assertion_evidence"]
        source["issuer_public_key_fingerprint_sha256"] = other_fp
        source["source_verification_evidence_hash"] = row["mm_authenticate_operator-mm_auth_verification_evidence_hash"]
        row["mm_create_attestation-mm_att_methodmesh_full_json"] = json.dumps(att)
        result = reconcile_submission(row, self.issuers, self.credentials)
        self.assertEqual(result.study_credential_status, "unknown_issuer")

    def test_unknown_credential(self):
        result = reconcile_submission(make_row(credential_id="cred_unknown"), self.issuers, self.credentials)
        self.assertEqual(result.study_credential_status, "unknown_credential")

    def test_issuer_mismatch(self):
        other_fp = "b" * 64
        credentials = {"cred_1": dict(self.credentials["cred_1"], issuer_public_key_fingerprint_sha256=other_fp)}
        result = reconcile_submission(make_row(), self.issuers, credentials)
        self.assertEqual(result.study_credential_status, "issuer_mismatch")

    def test_revoked(self):
        credentials = {"cred_1": dict(self.credentials["cred_1"], status="revoked", revoked_at_iso="2026-09-01T00:00:00Z")}
        result = reconcile_submission(make_row(), self.issuers, credentials)
        self.assertEqual(result.study_credential_status, "revoked")

    def test_tampered_binding_is_invalid(self):
        row = make_row()
        row["mm_event_payload_hash"] = "0" * 64
        result = reconcile_submission(row, self.issuers, self.credentials)
        self.assertEqual(result.study_credential_status, "invalid_evidence")
        self.assertFalse(result.attestation_binding_valid)


if __name__ == "__main__":
    unittest.main()
