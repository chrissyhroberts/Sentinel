# MethodMesh validation checklist

| ID | Check | Mode | Evidence | Status |
|---|---|---|---|---|
| MM-01 | NFC credential identifies the intended operator | Hybrid | Credential verification output | [ ] |
| MM-02 | Invalid, expired or wrong credential is rejected | Automated/Hybrid | Negative test output | [ ] |
| MM-03 | Attestation binds the intended operation/data commitment | Automated | Attestation payload and verification result | [ ] |
| MM-04 | Atomic-clock comparison records drift and device monotonic state | Automated | Clock comparison evidence | [ ] |
| MM-05 | Offline time is labelled as non-trusted and is never backdated | Automated | Offline test evidence | [ ] |
| MM-06 | RFC3161 evidence is verified when available | Automated | Token/certificate verification | [ ] |
| MM-07 | Credential, clock and attestation failure modes are handled safely | Hybrid | Negative test records | [ ] |
