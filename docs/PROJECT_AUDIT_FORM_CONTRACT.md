# Universal project audit form

Sentinel audits one explicitly configured Central project at a time. The
same Sentinel code and the same audit form can be used on any Central install;
only Central connection settings, the project allowlist, and the published
audit-form identifier are configuration.

The universal form is [sentinel_project_audit_v1.xml](sentinel_project_audit_v1.xml).
Publish it once in each audited project. Sentinel needs read permission on the
project's source forms and submit permission on this audit form. It never edits
or deletes source submissions.

## One project-level ledger

Every source form and every retained Central submission version is represented
by one audit-form submission. The deterministic audit instance ID is derived
from:

```text
project_id + source_form_id + logical_instance_id + source_version_id
```

The audit record contains the source identifiers, exact-byte hashes, Central
metadata, linked audit event/reason information, timestamp evidence, and—when
retained by policy—one exact source bundle attachment containing the original
XML, Collect audit file, and attachments.

The same form also stores one deterministic project checkpoint record. A new
run reads that checkpoint and the existing audit-form submissions before
fetching work, so completed versions are not repeated.

No project-specific field names, participant fields, XLSForm recipes, or
MethodMesh attestation payloads are required.
