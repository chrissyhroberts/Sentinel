# Sentinel validation checklist

| ID | Check | Mode | Evidence | Status |
|---|---|---|---|---|
| SEN-01 | Configuration contains one approved project and audit form | Automated | `--validate` report | [ ] |
| SEN-02 | Source forms, form versions and submission versions are discovered | Automated | `--validate` report | [ ] |
| SEN-03 | Deterministic audit IDs are unique and project-scoped | Automated | `--validate` report and unit tests | [ ] |
| SEN-04 | Exact source XML and applicable audit data are hashed | Automated | Independent hash check | [ ] |
| SEN-05 | Actors, edits, diffs and reasons are represented correctly | Automated/Hybrid | Controlled Central test | [ ] |
| SEN-06 | Run manifest and validation certificate are created | Automated | Central audit records and attachments | [ ] |
| SEN-07 | RFC3161 success, preferred outage and required outage paths behave correctly | Automated | Timestamp evidence | [ ] |
| SEN-08 | Prior manifest alteration or omission is detected | Automated | Chain-warning test | [ ] |
| SEN-09 | Interrupted runs resume without duplicate source records | Automated | Stop/resume test and reconciliation | [ ] |
| SEN-10 | Audit-form edits are detectable through manifest/hash evidence | Automated | Tamper simulation | [ ] |
| SEN-11 | No source data are edited, deleted or stored outside approved boundaries | Automated/Hybrid | API comparison and environment review | [ ] |
| SEN-12 | `--validate` remains read-only and returns machine-readable evidence | Automated | CLI test output | [ ] |
| SEN-13 | Active synthetic validation distinguishes pre-edit and post-edit XML hashes | Automated | `--validate-active` report | [ ] |

These checks validate Sentinel's behavior and evidence production. They rely on
ODK Central as the source system and do not replace the separate Central,
Collect, Enketo or MethodMesh checklists.
