# ODK Central API coverage inventory

This is the working gap analysis for Sentinel's ODK Central integration. It
compares the audit-relevant Central API surface documented by ODK with the
operations currently exposed by `sentinel_archive.central.CentralClient` and
used by the regular or Admin Sentinel runs.

The inventory was checked against the [ODK Central API overview](https://docs.getodk.org/central-api/),
[project management](https://docs.getodk.org/central-api-project-management/),
[form management](https://docs.getodk.org/central-api-form-management/),
[submission management](https://docs.getodk.org/central-api-submission-management/),
[accounts and users](https://docs.getodk.org/central-api-accounts-and-users/),
[system endpoints](https://docs.getodk.org/central-api-system-endpoints/), and
[OData endpoints](https://docs.getodk.org/central-api-odata-endpoints/).

## Status meanings

| Status | Meaning |
|---|---|
| Used | Sentinel calls it during a normal or Admin run and records or uses the result. |
| Available, not used | A client method exists, but the result is not currently part of the audit workflow. |
| Missing | The documented API operation is not implemented in Sentinel. |
| Permission-dependent | The operation exists, but the configured account may not be allowed to call it. |

## Projects and project metadata

| Documented Central operation | Client method | Current use | Status / audit implication |
|---|---|---|---|
| `GET /v1/projects` | `projects()` | Admin project discovery | Used by Admin; not part of the regular project ledger |
| `GET /v1/projects/{id}` | `project()` | Project metadata and health report | Used |
| `GET /v1/projects/{id}?forms=true` | `project()` | Project metadata request includes visible forms | Used indirectly |
| Extended project metadata (`X-Extended-Metadata`) | `project()` | Counts and allowed verbs where Central returns them | Partially used; report does not yet retain every returned field |
| `PATCH /v1/projects/{id}` | — | Rename/update project | Missing; detect through server audit only when enabled |
| `DELETE /v1/projects/{id}` | — | Delete project | Missing; detect through server audit only when enabled |
| Project restore/purge operations | — | Restore or permanently remove project | Missing; detect through server audit only when enabled |
| Project datasets summary (`datasets=true`) | — | Discover project datasets/entities | Missing |
| Project-level assignment listing | `project_assignments(project_id, role_id)` | Current project users and roles | Used, one role at a time |
| Project assignment summary API | — | Obtain all form assignments in one call | Missing; current method is more request-intensive |

## Forms, drafts and published versions

| Documented Central operation | Client method | Current use | Status / audit implication |
|---|---|---|---|
| `GET /v1/projects/{id}/forms` | `forms()` | Discover source, audit and validation forms | Used |
| `GET /v1/projects/{id}/forms?deleted=true` | `forms(deleted=True)` | Discover deleted forms and validate disposable-form deletion | Used for active validation and server-audit scoping; ordinary deleted-form lifecycle records remain permission-dependent |
| `GET /v1/projects/{id}/forms/{xmlFormId}` | `form_details(...)` | Read one form's complete metadata | Used in the project report |
| `POST /v1/projects/{id}/forms` | `create_form(...)` | Synthetic form-lifecycle validation | Used only with a disposable validation form |
| Form state update (`PATCH`) | — | Detect open/closing/closing changes | Missing as a direct operation; server-audit detection is optional |
| `DELETE /v1/projects/{id}/forms/{xmlFormId}` | `delete_form(...)` | Synthetic form-lifecycle validation | Deleted form is read back from Trash; restore/purge remain roadmap items |
| `GET /v1/projects/{id}/forms/{xmlFormId}/draft` | `form_draft(...)` | Inspect unpublished draft | Used when permitted; absence is recorded explicitly |
| `PUT/PATCH` draft definition operations | — | Detect draft replacement or deletion | Missing as direct reads; server-audit detection is optional |
| `POST .../draft/publish` | — | Detect publication | Missing as a direct operation; publication is visible through form versions and `form.update.publish` audit events |
| Draft XML and attachment inventory | `form_draft_xml(...)`, `form_attachments(..., draft=True)` | Hash/observe unpublished definition and expected files | Used; binaries are not copied routinely |
| Draft form attachment download | `form_attachment_bytes(..., draft=True)` | Controlled diagnostic download | Available, not used routinely |
| `GET .../forms/{xmlFormId}/versions` | `form_versions(form_id)` | Discover all published form versions | Used |
| `GET .../versions/{version}` | `form_version_details(...)` | Read published version metadata | Used in the project report |
| `GET .../versions/{version}.xml` | `form_version_bytes(..., "xml")` | Hash and retain form definition bytes | Used |
| `GET .../versions/{version}.xlsx` | `form_version_bytes(..., "xlsx")` | Retrieve published XLSX | Available, not used routinely |
| Published-version attachment listing | `form_version_attachments(...)` | Audit form-definition attachments | Used in the project report |
| Published-version fields | `form_version_fields(...)` | Retain parsed published schema | Used in the project report |
| `GET .../forms/{xmlFormId}/fields` | `form_fields(...)` | Read Central's parsed field schema | Used in the project report |
| `GET .../forms/{xmlFormId}/assignments` | `form_assignments(...)` | Form-specific role assignments | Used in the project report |
| `GET .../forms/{xmlFormId}/dataset-diff` | `form_dataset_diff(...)` | Related Dataset/property mapping | Used in the project report |

### Important form-registration finding

The current ledger does **not** create a separate record for `form.create`,
`form.update`, `form.update.draft.set`, `form.update.draft.replace`,
`form.update.publish`, `form.delete`, `form.restore` or `form.purge` unless
server-audit collection is enabled and the event is in scope.

A newly published form is discovered on the next regular run, and each of its
published versions is recorded as `source_form_version`. The exact deployed
XML is attached to that audit row, and the original XLSForm workbook is also
attached when Central retains an Excel source. This is intentionally separate
from participant-source archiving: a form definition is configuration evidence,
not participant data.
An unpublished draft has no published `/versions` entry, so it is not currently
registered in the source ledger. This is the specific gap behind the concern
about new forms and new form versions.

## Submissions, edits and attachments

| Documented Central operation | Client method | Current use | Status / audit implication |
|---|---|---|---|
| `GET .../forms/{xmlFormId}/submissions` | `submissions(form_id)` | Discover logical submissions | Used |
| `GET .../submissions/{instanceId}` | `submission(...)` | Confirm deterministic audit IDs / active validation | Used |
| `POST .../submissions` (OpenRosa/XML) | `submit(...)` | Write audit-form records | Used |
| `POST .../submissions?deviceID=...` (REST/XML) | `create_validation_submission(...)` | Active synthetic validation | Used |
| `PUT .../submissions/{instanceId}` | `update_validation_submission(...)` | Active synthetic edit validation | Used |
| `DELETE .../submissions/{instanceId}` | — | Detect or perform soft deletion | Missing directly; server-audit detection is optional |
| Submission restore/purge | — | Detect or perform restoration/permanent deletion | Missing directly; server-audit detection is optional |
| `GET .../submissions/{instanceId}/versions` | `versions(...)` | Discover original and edited versions | Used |
| `GET .../versions/{versionId}` | `version_metadata(...)` | Read individual version metadata | Available, not used by normal crawl |
| `GET .../versions/{versionId}.xml` | `version_xml(...)` | Hash exact source XML | Used |
| `GET .../submissions/{instanceId}.xml` | `submission_xml(...)` | Read current submission XML | Used by active validation support; not the normal historical crawl |
| `GET .../versions/{versionId}.geojson` | — | Read geospatial representation | Missing |
| `GET .../versions/{versionId}/attachments` | `version_attachments(...)` | Inventory attachment presence | Used |
| `GET .../versions/{versionId}/attachments/{filename}` | `attachment_bytes(...)` | Hash/read attachment bytes | Used where required by validation/evidence |
| `POST .../attachments/{filename}` | `upload_attachment(...)` | Attach Sentinel evidence to audit submissions | Used |
| `DELETE .../attachments/{filename}` | — | Detect or clear attachments | Missing directly; server-audit detection is optional |
| `GET .../submissions/{instanceId}/audits` | `audits(...)` | Read submission-specific Central audit events | Used |
| `GET .../submissions/{instanceId}/comments` | `comments(...)` | Link comments to edits/reasons | Used |
| `POST .../submissions/{instanceId}/comments` | — | Create comments | Missing; Sentinel only reads comments |
| `GET .../submissions/{instanceId}/diffs` | `diffs(...)` | Read old/new field values | Used |
| Review-state operations | — | Read/set/clear review state | Missing |
| CSV/ZIP submission export | — | Complete bulk export | Missing; source XML-by-version is currently the authoritative archive path |

## Accounts, roles, assignments and actors

| Documented Central operation | Client method | Current use | Status / audit implication |
|---|---|---|---|
| `POST /v1/sessions` | `login(...)` | Authenticate regular/admin run | Used |
| Session termination | — | Explicit logout/session closure | Missing |
| `GET /v1/users` | `users()` | Visible Web User inventory | Used |
| `GET /v1/users/{id}` | `user(...)` | Map actor IDs to email addresses | Used, cached |
| Web User create/update/delete/password operations | — | Detect user lifecycle | Missing directly; Admin server-audit collection can capture events |
| `GET /v1/roles` | `roles()` | Role definitions and verbs | Used |
| Individual role details | — | Read one role in isolation | Missing; list response is currently sufficient for the snapshot |
| `GET /v1/assignments` | `assignments()` | Site-wide assignment inventory | Used by Admin/platform snapshot where permitted |
| Project assignment listing | `project_assignments(...)` | Project user-role mapping | Used |
| Form assignment listing | `form_assignments(...)` | Form-specific access mapping | Used in the project report |
| App User listing | `app_users(...)` | Project App User inventory / last-used metadata | Used |
| App User create/update/delete | — | Detect or perform App User lifecycle | Missing directly; server-audit/Admin coverage only |
| `GET /v1/projects/{id}/actor-properties` | `actor_properties(...)` | Registered actor-property names and values | Used in the project report |
| App User property APIs | — | Read one actor's property mutation history | Missing; lifecycle events require server audit |
| Public Link listing/details/property APIs | `public_links(...)` | Public access inventory without retaining link tokens | Used in the project report |
| Project actor-property APIs | `actor_properties(...)` | Property definitions and distinct values | Used in the project report |

## Server audit and system information

| Documented Central operation | Client method | Current use | Status / audit implication |
|---|---|---|---|
| `GET /v1/audits` with time window/pagination | `server_audits(...)` | Optional project-filtered lifecycle/event log | Used only when `server_audit_enabled=true` or Admin run |
| Extended audit actor/actee metadata | `server_audits(...)` | Actor attribution and event context | Used where permission allows |
| `GET /v1/config/{key}` | `system_config(key)` | Read selected Central configuration | Available, not currently included in regular report |
| `GET /v1/analytics/preview` | `analytics_preview()` | Usage-report preview | Available, not currently included |
| Server/version/health endpoint | — | Central version, uptime, disk space | Not available through the ordinary documented project API; requires host/admin access or deployment-specific endpoint |

The Central documentation lists audit events for form creation, draft changes,
publishing, deletion/restoration, user sessions, user changes, App User
assignment, submission creation/update/deletion/restoration and many other
operations. These are the correct way to detect lifecycle events that are not
represented by a published form version or a retained submission version.

## Datasets, Entities, OpenRosa and OData

These are documented Central API surfaces but are outside the current Sentinel
source-form crawl:

| Surface | Current Sentinel status | Consequence |
|---|---|---|
| Datasets and Entity Lists | Configuration-gated `datasets(...)`, `dataset_entities(...)` | Out of scope for the current study; retained on the roadmap |
| OpenRosa form list/download | Missing | Sentinel uses the REST API; Collect-facing discovery is not independently checked |
| OpenRosa submission endpoint | Not used directly | Audit writes use Central REST/XML submission calls |
| OData data documents and `$filter` | Missing | No independent tabular/export reconciliation is performed |
| Encryption key and encrypted export endpoints | Missing | Managed-encryption state is not independently verified by Sentinel |

## Initial priorities

The remaining priorities are:

1. Add a lightweight **form lifecycle record** for draft/publish/delete/restore
   events, preferably from the server audit feed when available and from a
   project-form inventory comparison otherwise. Newly published forms and
   versions are already registered by the regular crawl.
2. Store the complete form metadata response, including `createdBy`,
   `publishedAt`, `lastSubmission`, `reviewStates`, state and allowed verbs.
3. Add published-version detail and version-attachment inventory so a form
   version is not represented only by its XML hash.
4. Add form-specific assignments and public-link/App-User access inventory.
5. Decide whether Datasets/Entities are in study scope; if they are, they need
   their own crawl and audit record types.
6. Add an optional OData/CSV reconciliation check for projects where a second
   export representation is required.

## Second-pass findings

The API review also identified these opportunities for additional monitoring.
They are deliberately separated from the ordinary project QA summary because
some require extra permissions, can expose more data, or need a new evidence
collector.

### High-value additions

| Opportunity | Why it matters | Best evidence form |
|---|---|---|
| Retain Central extended form metadata | Captures `reviewStates`, `lastSubmission`, creator and other Central-maintained status values | Project QA attachment; no extra ledger line unless a value changes |
| Hash and inventory draft XML | Detects an unpublished form change before publication | Separate draft-change line when the draft hash changes; current draft state in QA report |
| Inventory published-version metadata and attachments | Confirms publisher, version timestamps and form-definition media | `source_form_version` line plus attachment inventory |
| Capture form-level assignments | Detects access that project-level assignments alone do not show | QA attachment; assignment changes become Central event lines when available |
| Capture review-state counts and transitions | Distinguishes ordinary edits from Approved/Rejected/Has Issues workflow | QA summary plus separate `central_submission_update` event where Central logs it |
| Add a Central export reconciliation | Compares retained XML-derived counts with a CSV/OData representation | Validation evidence package |

### Permission-dependent additions

| Opportunity | Limitation |
|---|---|
| Full server audit window | Requires the privileged audit feed; this is the authoritative source for form creation, draft publication, deletion/restoration, user changes, logins and App User/Public Link lifecycle events |
| Public Link inventory | Requires the relevant project/form access and a new read collector |
| System configuration and usage preview | Administrator-only or configuration-dependent; suitable for the monthly Admin Sentinel snapshot |
| Encryption-key and managed-encryption status | Requires explicit handling of secrets; Sentinel should record configuration/status, never passphrases |
| Central backup endpoint | Technically available to administrators, but downloading a database backup would violate the normal Sentinel data-minimisation boundary and should remain an explicit separate operation |

### New API domains, not just missing fields

Datasets and Entities are a separate audit domain. If a study uses them,
Sentinel needs logical dataset/entity identifiers, entity version and conflict
records, processing errors, deletions/restores/purges, and the relevant form
mapping. They should not be folded into the ordinary submission ledger.

OpenRosa and OData are also different observation surfaces. REST access proves
what Central exposes through the REST API; it does not prove that Collect can
download the form, that Enketo can render it, or that an OData/CSV export
reconciles with the retained XML. Those belong in the component validation
forms and evidence package, not as duplicate source records.

Finally, a regular run cannot observe host uptime, disk space, CPU, memory,
database backup status or container health through the ordinary project API.
Those remain Admin Sentinel or deployment-monitoring responsibilities. The
Central system API does expose usage-report preview and server audit resources,
but those are not substitutes for host health metrics.
