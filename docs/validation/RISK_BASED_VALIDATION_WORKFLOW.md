# Sentinel risk-based validation workflow

This workflow turns the checklist into an evidence-based release decision. It
is deliberately proportionate: effort is concentrated on data and processes
that could affect participant safety, rights, trial conclusions or the ability
to reconstruct the record.

## Stage 1 — Define the intended use

1. Name the trial, project, Central installation and source forms.
2. Draw the data flow from operator/NFC credential through Collect and Central
   to Sentinel and the TMF.
3. Decide which records are source records and which are derived integrity
   evidence.
4. Identify critical-to-quality fields and decisions.
5. Record the intended use and exclusions in the checklist.

**Gate:** sponsor/system owner approves the scope before validation testing.

## Stage 2 — Assess risk and write requirements

1. Identify failure modes: missing version, wrong actor, altered XML, missing
   reason, untrusted time, incomplete manifest, duplicate run, Central outage
   and unauthorised audit-form change.
2. Rate impact, likelihood and detectability.
3. Convert high-risk failure modes into testable requirements.
4. Define the evidence required to pass each requirement.
5. Decide whether server-wide Central audit collection is needed. It is
   optional and should remain off for the basic proportionate workflow unless
   forensic lifecycle evidence is specifically required.

**Gate:** critical requirements and acceptance criteria are approved.

## Stage 3 — Baseline the controlled configuration

Record, preserve and approve:

- Sentinel commit and runtime/dependencies;
- Central version and project settings;
- audit-form XLSForm and published version;
- source-form versions and Collect audit settings;
- Central roles and Sentinel account permissions;
- timestamp policy and TSA configuration;
- configuration checksum, excluding secrets.

Do not place passwords, tokens or participant data in the repository.

**Gate:** the validation environment is reproducible.

## Stage 4 — Execute risk-based testing

Test critical requirements first, then supporting behavior. Each test record
should contain:

```text
Test ID:
Requirement:
Preconditions:
Input/test data:
Expected result:
Observed result:
Evidence link:
Tester/date:
Pass/fail:
Deviation:
```

At minimum, test original submissions, multiple edits, reasons, actor mapping,
source hashes, Collect audit hashes, RFC3161 success, TSA outage, manifest
chaining, interrupted runs, duplicate runs, permission failures and an
independent reconstruction from Central.

**Gate:** all critical tests pass or have approved deviations.

## Stage 5 — Review deviations and approve release

1. Classify failures as critical, major or minor.
2. Open remediation/CAPA items where required.
3. Document residual risk and compensating controls.
4. Approve the production release and lock the tested versions.
5. Record the release in the TMF/quality system.

**Gate:** sponsor/system owner authorises production use.

## Stage 6 — Controlled operation

For each production run:

1. Confirm the configured project and audit form.
2. Run Sentinel with the controlled release.
3. Review the summary and any warnings.
4. Confirm the timestamp status and manifest chain status.
5. Open the `validation_certificate` record and review its automated checks.
6. Investigate pending, missing, duplicate or changed records.
7. Preserve the manifest, validation certificate, timestamp token and TSA
   certificate in Central.
8. Record the run review and exceptions in the quality system.

Sentinel's idempotent deterministic IDs allow a stopped run to be repeated.
An RFC3161 outage under preferred policy is an exception to review, not an
automatic loss of the source archive.

## Stage 7 — Periodic review and change control

Review at a risk-based frequency and whenever there is a significant change:

- Sentinel code or dependencies;
- Central version or configuration;
- audit-form version;
- source-form audit settings;
- NFC credential or identity process;
- TSA endpoint or certificate chain;
- roles, permissions or retention rules;
- trial protocol or critical data assessment.

Each change receives an impact assessment. Re-test affected critical
requirements, approve the change, preserve the new baseline and update the
TMF evidence.

## What this workflow does not claim

Passing these tests does not by itself make a trial compliant. The sponsor
remains responsible for the quality system, source-data determination,
computerised-system oversight, training, records retention, data review and
inspection readiness.
