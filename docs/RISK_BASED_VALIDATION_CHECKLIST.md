# Sentinel risk-based validation checklist

Status values used in this checklist:

- `[ ]` not started
- `[-]` in progress
- `[x]` complete with evidence linked
- `[!]` exception or remediation required
- `[N/A]` not applicable, with justification recorded

This is a working sponsor checklist, not a claim that Sentinel is validated.
Each completed item should point to an approved document, test record, Central
configuration snapshot, or other retained evidence.

## A priori draft baseline

The following can be entered before trial-specific testing. They describe the
current Sentinel architecture and proposed intended use; they still require
review and approval by the sponsor/system owner.

### Proposed intended use

- **Purpose:** project-level integrity ledger and reconstruction aid for ODK
  Central trial records.
- **Source system:** ODK Central retains the original source submissions and
  their retained versions. Sentinel does not replace Central or copy the
  source dataset into a second form.
- **Sentinel evidence:** exact Central submission bytes are hashed; Central
  version metadata, actor identity, server time, diffs, applicable Collect audit
  data and timestamp-manifest evidence are recorded.
- **Identity:** MethodMesh NFC credentials identify the operator where the
  relevant form/process uses them. This is not automatically an electronic
  signature or investigator approval.
- **Time:** Central server timestamps and RFC3161 evidence are used where
  available. Offline/local time is labelled as non-trusted time evidence and
  is not backdated.
- **Scope:** one explicitly configured Central project per run; the server-wide
  Central audit feed is disabled by default.
- **Storage boundary:** no password, token, participant dataset or unapproved
  local research archive is retained by Sentinel.
- **Out of scope:** canonical XLSForm recipe reconstruction,
  `previous_attestation_hash` per-record chaining, prevention of Central
  administrator actions, and ordinary web logout evidence where Central does
  not emit it.

Sponsor/system-owner decision:

```text
[ ] Proposed baseline accepted as intended use
[ ] Amendments required
Owner:
Date:
Approval/evidence reference:
```

### Proposed system boundary

```text
Operator/NFC credential
        -> ODK Collect and Collect audit.csv where enabled
        -> ODK Central source form and retained versions
        -> Sentinel read/hash/diff/reason process
        -> Central project audit form
        -> RFC3161 TSA when enabled/available
        -> TMF/inspection evidence through Central
```

Confirm before release:

- [ ] Project and source-form allowlist approved.
- [ ] Audit form ID and published version approved.
- [ ] Central remains the authoritative source-data repository.
- [ ] Sentinel account is restricted to required read/submit permissions.
- [ ] Timestamp policy is approved as `preferred` or `required`.
- [ ] `server_audit_enabled` is approved as `false` for the proportionate
  baseline, unless a separate forensic requirement exists.

### Evidence already available from the current implementation

- [x] Deterministic IDs and resume/duplicate behavior are covered by automated
  tests.
- [x] Exact source XML and audit metadata hashing are implemented.
- [x] Central actor-to-email mapping is implemented where permitted.
- [x] Central edit diffs and Collect change reasons are implemented.
- [x] RFC3161 manifest, token and certificate handling is implemented.
- [x] Run-level manifest chaining and prior-manifest verification are
  implemented.
- [x] Preferred timestamp failure and interrupted-run behavior are defined.

These checkmarks mean implemented or tested in the repository, not validated
for a regulated trial. The sponsor must still link each item to controlled
test evidence and approve its use.

## 1. Intended use and scope

- [ ] Define the trial, project and Central installation in scope.
- [ ] Identify whether ODK Collect is the source-record system, a transcription
  system, or both for each data flow.
- [ ] Identify critical-to-quality data and processes: eligibility,
  randomisation, dosing, safety, primary endpoints, blinding and stopping
  decisions.
- [ ] Define the intended use of NFC identity evidence: operator identification,
  electronic signature, or both.
- [ ] Define the intended use of Sentinel: integrity ledger, monitoring aid,
  archive index, or another approved purpose.
- [ ] Define what Sentinel does not do: it does not replace Central, the
  Collect audit trail, investigator oversight, source verification, or the
  sponsor TMF.
- [ ] Approve the system boundary and data-flow diagram.

Evidence:

```text
Owner:
Approval date:
Scope document:
Data-flow diagram:
Critical data assessment:
```

## 2. Risk assessment and requirements

- [ ] Maintain a risk assessment using impact, likelihood and detectability.
- [ ] Classify requirements as critical, major or supporting.
- [ ] Define acceptance criteria for source identity, completeness,
  contemporaneity, attributable changes, reason capture and reconstruction.
- [ ] Define offline behavior and the meaning of `time_assurance` states.
- [ ] Define the required behavior when RFC3161 is unavailable.
- [ ] Define the required behavior for Central outage, partial run, duplicate
  run, malformed record and permission failure.
- [ ] Define retention, backup, restore and disaster-recovery requirements.
- [ ] Define the audit-trail review and exception-escalation process.

Minimum critical requirements:

| ID | Requirement | Risk if absent | Acceptance evidence |
|---|---|---|---|
| R-01 | Every retained source version is discovered and represented once | Missing or incomplete source history | Controlled test plus reconciliation |
| R-02 | Exact Central XML bytes are hashed without canonical re-serialization | Hash does not represent source record | Hash comparison test |
| R-03 | Actor, Central time and source identifiers are retained | Attribution/reconstruction failure | End-to-end test |
| R-04 | Edits retain old/new values and applicable reasons | Unexplained data changes | Edit/reason test |
| R-05 | Run manifests are timestamped or explicitly marked unavailable | Weak contemporaneous integrity evidence | TSA and outage tests |
| R-06 | Manifest chain changes are detectable | Undetected ledger tampering | Alteration/deletion simulation |
| R-07 | Reruns are idempotent and recoverable | Duplicate or missing archive records | Interrupted-run test |
| R-08 | Records can be reconstructed for inspection | Regulatory review failure | Mock inspection exercise |

## 3. System and configuration control

- [ ] Record the Sentinel repository commit, Python/runtime version and
  dependency versions used for validation.
- [ ] Record the ODK Central version and relevant server configuration.
- [ ] Record the published audit XLSForm ID and version.
- [ ] Record every source-form version in the trial baseline.
- [ ] Confirm Collect audit logging and change-reason settings for applicable
  forms.
- [ ] Confirm Central roles and permissions for source forms and the audit
  form.
- [ ] Confirm the Sentinel account has only required read/submit permissions.
- [ ] Confirm `server_audit_enabled` is intentionally true or false.
- [ ] Confirm timestamp policy, TSA endpoint and certificate handling.
- [ ] Confirm configuration contains no passwords, tokens or participant data.
- [ ] Approve the controlled release package before production use.

## 4. Functional and integrity testing

### Source and version coverage

- [ ] Discover every configured source form.
- [ ] Archive a published form version.
- [ ] Archive an original submission.
- [ ] Archive multiple submissions for the same form.
- [ ] Archive multiple retained versions of one submission.
- [ ] Confirm a rerun skips existing deterministic records.
- [ ] Add a new submission and confirm only the new record is pending.
- [ ] Add a new form version and confirm only the new version is pending.

### Edits, reasons and actors

- [ ] Edit one field and verify old/new values.
- [ ] Edit multiple fields and verify the current version only.
- [ ] Record a Collect change reason and verify `linked_collect_audit`.
- [ ] Record a Central version-linked reason and verify its status.
- [ ] Add Central comments around multiple edits and verify the documented
  activity-stack behavior.
- [ ] Verify actor IDs resolve to email addresses where Central permits it.
- [ ] Test an App User or non-email actor and verify the safe fallback.

### Hashing and timestamps

- [ ] Recalculate a source XML hash independently and compare it with Sentinel.
- [ ] Verify the Collect audit hash independently.
- [ ] Obtain a successful RFC3161 token and verify its message imprint.
- [ ] Verify manifest hash, token and certificate attachments.
- [ ] Simulate TSA unavailability under preferred policy.
- [ ] Simulate TSA unavailability under required policy.
- [ ] Verify offline/local time evidence is never presented as trusted time.
- [ ] Verify the next manifest carries the previous manifest ID and hash.
- [ ] Alter a prior manifest attachment and verify a chain warning.
- [ ] Remove or alter an audit record and verify the resulting exception.

### Failure and recovery

- [ ] Stop a run after some records have been submitted and rerun it.
- [ ] Interrupt during a network retry and rerun it.
- [ ] Test Central read permission failure.
- [ ] Test audit-form submit permission failure.
- [ ] Test malformed source XML or attachment response.
- [ ] Confirm source data is never edited or deleted by Sentinel.
- [ ] Confirm no unapproved local archive remains after a run.

## 5. Procedural and organisational controls

- [ ] Approve an SOP for Sentinel operation.
- [ ] Approve an SOP for reviewing Sentinel exceptions and chain warnings.
- [ ] Approve an SOP for access provisioning, review and revocation.
- [ ] Approve an SOP for changes to Sentinel code, configuration and forms.
- [ ] Train operators, reviewers and administrators.
- [ ] Define incident, deviation and CAPA handling.
- [ ] Define periodic review frequency and responsible role.
- [ ] Define how Sentinel evidence is indexed in the TMF.
- [ ] Perform a mock inspection using a randomly selected participant record.

## 6. Release decision

- [ ] All critical requirements pass.
- [ ] All critical deviations have approved remediation or documented
  justification.
- [ ] Validation summary approved by the sponsor/system owner.
- [ ] Production release version tagged and preserved.
- [ ] First production run reconciled and reviewed.
- [ ] Review schedule entered into the quality system.

Release decision:

```text
System/release:
Trial/project:
Decision:  [ ] approved  [ ] approved with conditions  [ ] not approved
Conditions/deviations:
Approver:
Date:
```

## References

- [MHRA GCP compliance and ICH E6(R3)](https://www.gov.uk/guidance/clinical-trials-for-medicines-compliance-with-ich-e6-good-clinical-practice-gcp-in-the-united-kingdom)
- [MHRA GxP data integrity guidance](https://www.gov.uk/government/publications/guidance-on-gxp-data-integrity)
- [MHRA archiving and retention guidance](https://www.gov.uk/government/publications/clinical-trials-for-medicines-archiving-and-retention-of-clinical-trial-records)
