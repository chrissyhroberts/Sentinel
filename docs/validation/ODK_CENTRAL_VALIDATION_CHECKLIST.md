# ODK Central validation checklist

| ID | Check | Mode | Evidence | Status |
|---|---|---|---|---|
| CEN-01 | Project ID and audit form are configured and discoverable | Automated | `--validate` report | [ ] |
| CEN-02 | Source forms and published versions are discoverable | Automated | `--validate` report | [ ] |
| CEN-03 | Submission versions can be read with the Sentinel account | Automated | `--validate` report and run summary | [ ] |
| CEN-04 | Audit form submissions can be read | Automated | `--validate` report | [ ] |
| CEN-05 | Audit-form submit permission works | Hybrid | Controlled test submission/run certificate | [ ] |
| CEN-06 | Edit versions expose old/new values and Central timestamps | Hybrid | Central test submission and API response | [ ] |
| CEN-07 | Change reasons/comments are available for the tested edit path | Hybrid | Central activity view and API evidence | [ ] |
| CEN-08 | Source records remain unchanged by Sentinel | Automated | API comparison before/after | [ ] |
| CEN-09 | Retention, backup and restore arrangements are approved | Witnessed | Infrastructure/quality evidence | [ ] |

The automated Central checks validate the API surface available to the
configured project account. They do not validate Central host infrastructure,
database health, disk space, uptime, backups or Server Administrator-only
audit feeds.
