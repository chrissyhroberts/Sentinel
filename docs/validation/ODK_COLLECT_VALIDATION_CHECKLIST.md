# ODK Collect validation checklist

| ID | Check | Mode | Evidence | Status |
|---|---|---|---|---|
| COL-01 | Approved Collect version and device configuration are recorded | Automated/Hybrid | Device/configuration snapshot | [ ] |
| COL-02 | Operator identity/NFC step returns the expected identity evidence | Hybrid | MethodMesh test output | [ ] |
| COL-03 | Normal form entry creates the expected source XML | Automated | Central XML/hash comparison | [ ] |
| COL-04 | Collect audit logging is enabled where required | Hybrid | Form/device configuration and audit attachment | [ ] |
| COL-05 | A field edit records old/new values and the entered reason | Hybrid | Collect audit file and Central version | [ ] |
| COL-06 | Offline entry and later synchronisation preserve source/version order | Hybrid | Controlled offline test | [ ] |
| COL-07 | Interrupted synchronisation resumes without duplicate source records | Automated/Hybrid | Central reconciliation report | [ ] |
