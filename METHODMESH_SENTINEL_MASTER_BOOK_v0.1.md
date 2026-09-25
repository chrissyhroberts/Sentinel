# MethodMesh Sentinel Master Book

**Document:** MethodMesh Sentinel Master Book  
**Edition:** v0.1 — foundation draft  
**Revision date:** 2026-09-23  
**Status:** Architecture authority candidate and implementation foundation; not yet a validated production clinical-trial system  
**Primary use case:** Regulated and research-grade trials using ODK Central/Collect, with MethodMesh for local assurance/capabilities and Sentinel for governed orchestration, reconciliation, verification and audit evidence  
**Product model:** ODK Central + ODK Collect + MethodMesh Android + MethodMesh Sentinel Desktop + Sentinel Service + Governance Sidecar + independent backup + third-party timestamp authority where required

---

## Document purpose

This Master Book is the developing single architectural authority for **MethodMesh Sentinel**: the controlled toolkit and service layer that turns ODK + MethodMesh into a governed trial platform without replacing ODK as the authoritative data system.

It absorbs and extends the architecture previously described in:

- `TRIAL_PLATFORM_V1_0_SPEC_20260918.md`;
- the regulated-trial portions of the MethodMesh Master Book;
- the implemented MethodMesh XLSForm Compiler v0.3.0 contract;
- the implemented MethodMesh FULL provenance envelope v3;
- the tested NFC credential, clock-assurance and attestation workflow.

The central architectural change from the original trial-platform plan is that **Sentinel is now explicitly a product with both an operator plane and a server/control plane**:

1. **MethodMesh Sentinel Desktop** — the human operator interface for controlled tasks;
2. **Sentinel Service** — the authenticated execution/orchestration service, normally running on the controlled VM;
3. **Sentinel task engines** — deterministic components such as the MethodMesh XLSForm compiler;
4. **ODK Governance Sidecar** — the durable append-only governance ledger for the trial.

The existing XLSForm compiler is the first implemented Sentinel task engine.

The long-term design objective is that an authorised operator can use one coherent desktop application to perform controlled actions such as:

- compile an ODK form into a MethodMesh-aware regulated release;
- validate and prepare a form for deployment;
- deploy, supersede or retire a governed form version;
- update the governed roles-and-responsibilities declaration;
- register, replace or revoke credentials/public keys;
- inspect Sentinel runs and discrepancies;
- request integrity verification;
- inspect query, deviation, access and document-control state;
- invoke controlled archive/export operations.

The GUI is not itself the authority. In regulated operation, actions pass through the Sentinel Service, which authenticates and authorises the request, invokes the relevant task engine, and records the action and outcome in the trial Governance Sidecar.

---

# 1. MethodMesh Sentinel in one page

MethodMesh Sentinel is a companion platform around ODK, not a replacement for it.

```text
                         HUMAN OPERATOR
                              │
                              ▼
                  ┌─────────────────────────┐
                  │ MethodMesh Sentinel     │
                  │ Desktop                 │
                  │                         │
                  │ controlled GUI          │
                  │ task submission         │
                  │ review / reconciliation │
                  └────────────┬────────────┘
                               │ authenticated task request
                               ▼
                  ┌─────────────────────────┐
                  │ Sentinel Service        │
                  │ controlled VM           │
                  │                         │
                  │ authn/authz             │
                  │ task orchestration      │
                  │ ODK/API interaction     │
                  │ verification            │
                  │ reconciliation          │
                  │ scheduling              │
                  └───────┬─────────┬───────┘
                          │         │
                  task engine(s)    │
                          │         │
              ┌───────────▼───┐     │
              │ form.compile  │     │
              │ compiler      │     │
              └───────────────┘     │
                                    ▼
                         ODK CENTRAL
                DURABLE AUTHORITATIVE DATA PLANE
                    │                   │
                    │                   │
              Study Project       Governance Sidecar
                    ▲                   ▲
                    │                   │
                    └────────┬──────────┘
                             │
                             │ sync / evidence
                             ▼
                    ODK COLLECT ↔ METHODMESH
                    field data    local assurance
                                  + capabilities
```

The system separates four concerns:

- **ODK** owns authoritative study records and durable ODK-native history.
- **MethodMesh** owns local capability execution and assurance at the person/device/action boundary.
- **Sentinel Service** owns governed orchestration, verification, reconciliation and automated controls.
- **Governance Sidecar** owns durable append-only governance evidence.

The core regulated staff-submission pattern is:

```text
ODK form instance
    │
    ├── MethodMesh NFC credential + PIN verification
    │       └── verified credential execution ID
    │
    ├── ODK calculates deterministic commitment over governed form content
    │       └── SHA-256 payload/object commitment
    │
    └── MethodMesh attestation.create
            ├── reuses the verified NFC execution
            ├── binds study/form/version/form-instance context
            ├── binds exact commitment + commitment recipe
            ├── records common time assurance
            ├── signs the attestation
            └── obtains/validates RFC 3161 timestamp evidence according to policy

                    ▼ sync

Sentinel independently reconstructs and verifies the evidence
                    ▼
Governance Sidecar verification / ledger events
```

The result is not “compliance by app”. It is a layered evidence system supporting regulated governance.

---

# 2. Authority, scope and normative language

## 2.1 Authority

Once adopted, this Master Book is intended to supersede the original `Trial Platform v1.0 Architecture — ODK Central + Sentinel + MethodMesh` as the cross-system architecture authority.

Authority remains layered:

- **this Master Book** governs MethodMesh Sentinel product architecture, cross-system responsibility boundaries, task contracts, regulated MethodMesh/ODK integration and Sidecar evidence;
- the **MethodMesh Master Book** remains the authority for the general MethodMesh Android application and capability framework except where this document defines the regulated-trial profile;
- **Sentinel schemas and released code** implement the generic service/task/ledger contracts defined here;
- each approved **trial-design document/YAML** governs trial-specific policy within the approved Sentinel schema;
- SOPs, delegation logs, role definitions, institutional IT controls and validation documentation govern responsibilities software cannot determine by itself.

A lower layer MUST NOT silently broaden the authority of another layer.

Examples:

- a MethodMesh capability MUST NOT become a hidden trial-specific Sentinel policy engine;
- the Sentinel Desktop MUST NOT directly mutate governed trial state behind the Sentinel Service;
- Sentinel MUST NOT become a real-time network dependency for ordinary offline field identity assurance;
- the compiler MUST NOT invent visit/event semantics merely because it has a form-instance UUID.

## 2.2 Normative language

The terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY** and **REQUIRED** are normative.

Where this document describes software that has not yet been implemented, the requirement is architectural rather than a claim of current functionality.

## 2.3 Implementation-state labels

This book uses four implementation-state labels:

- **IMPLEMENTED** — present in the current code path and exercised sufficiently to establish the architecture.
- **IMPLEMENTED / QUALIFY** — implemented but still requiring formal validation/qualification for intended regulated use.
- **PLANNED** — accepted architecture but not yet implemented.
- **OPEN** — architecture or policy remains to be decided.

---

# 3. Core design principles

## 3.1 ODK remains authoritative

ODK Central remains the primary persistent data plane for:

- study data;
- submission history and ODK-native audit evidence;
- trial metadata;
- Sentinel-generated governance events;
- queries and query history;
- deviations and violations;
- access-governance records;
- document/form control metadata and hashes;
- Sentinel run evidence;
- integrity attestations and verification outcomes;
- signature/identity-assurance records;
- lock and archive-control records.

Sentinel MAY use transient local working state during execution. Unique clinical or governance evidence MUST NOT exist only on the Sentinel host as its final authoritative representation.

## 3.2 Operational data and governance evidence are separated

Each regulated trial has, at minimum:

- a **Study Project** for operational study/source records;
- a **Governance Sidecar Project** for restricted governance and audit evidence.

The Study Project answers:

> What is the current valid operational trial state?

The Governance Sidecar answers:

> How did the trial data, configuration, permissions, controlled artefacts and regulated workflows reach that state?

## 3.3 Sentinel is generic and multi-trial

Sentinel MUST NOT contain hidden trial-specific branches such as:

```text
if trial == "TRIAL_A":
    ...
```

Trial policy belongs in governed configuration, schemas and instruments.

The same Sentinel engine should support one pilot trial and many concurrent trials without architectural redesign.

## 3.4 Governance evidence is append-only

Governance is represented as events, not by repeatedly replacing a single mutable row.

Examples include:

- role declaration created;
- role declaration superseded;
- query opened;
- query response received;
- deviation opened;
- access discrepancy detected;
- form release compiled;
- form release deployed;
- credential registered;
- credential revoked;
- verification succeeded/failed;
- Sentinel run opened/closed.

Current state MAY be materialised for dashboards, but the underlying events remain reconstructable.

## 3.5 Field assurance remains offline-capable

MethodMesh-mediated identity verification, local confirmation and attestation MUST be capable of running without Sentinel, ODK Central or institutional identity services being online at the moment of the field action.

Sentinel verifies and reconciles evidence later.

Sentinel is not the real-time field permission oracle.

## 3.6 MethodMesh capabilities remain generic

Trial-specific workflows call generic MethodMesh capabilities.

A new trial SHOULD NOT require new MethodMesh Android code simply to express:

- a new protocol;
- a different form;
- a different study identifier;
- a different role list;
- a different query threshold;
- a different assurance policy.

## 3.7 Evidence strength must not be overstated

A supplied identifier is not automatically an authenticated identity.

A successful hash operation is not automatically proof of regulatory originality.

A timestamp is not automatically trusted time.

A cryptographically valid credential is not automatically issued by an approved trial authority.

The platform MUST preserve the evidentiary basis of each claim.

## 3.8 Compliance is systemic

MethodMesh Sentinel supplies technical controls and evidence. Regulatory compliance remains a property of the complete system of:

- software;
- approved design;
- validation;
- SOPs;
- human roles;
- training;
- change control;
- security;
- backup/recovery;
- archive/retention;
- review and oversight.

---

# 4. Product architecture

## 4.1 Field plane

The field plane consists primarily of:

- ODK Collect or supported ODK-compatible collection surface;
- MethodMesh Android;
- governed local credentials where used;
- supported instruments/sensors where used.

The field plane creates the operational record and local evidence.

## 4.2 Durable data plane

ODK Central is the durable authoritative data plane.

The platform does not introduce a separate Sentinel clinical database.

## 4.3 Operator plane

**MethodMesh Sentinel Desktop** is the planned human-facing control surface.

It is intended to make controlled operations understandable and reproducible without requiring routine command-line or direct-server access.

The Desktop SHOULD eventually expose task-oriented actions such as:

```text
Forms
  Compile form
  Validate release
  Deploy form
  Compare deployed form to approved release
  Supersede/retire form

Governance
  Update roles and responsibilities
  Review access discrepancies
  Register/revoke credential
  Register controlled document
  Review outstanding actions

Verification
  Verify MethodMesh evidence
  Verify release bundle
  Run Sentinel reconciliation
  Inspect failed checks
  Inspect cryptographic chain

Trial operations
  Register/configure trial
  Run Sentinel manually
  Review run status
  Prepare certified copy/archive package
```

The Desktop is a presentation and command surface. It SHOULD NOT independently implement task logic that is also implemented on the server.

## 4.4 Control plane

The **Sentinel Service** is the planned authoritative task/orchestration service running on the controlled VM.

Responsibilities include:

- operator authentication;
- authorisation against governed roles;
- task request validation;
- task ID assignment;
- task execution/orchestration;
- ODK Central interaction;
- Sidecar event persistence;
- verification;
- reconciliation;
- scheduled Sentinel runs;
- structured error reporting;
- controlled access to deployment secrets.

The Desktop and CLI SHOULD invoke the same underlying task contracts.

## 4.5 External trust and resilience services

The architecture may include:

- RFC 3161 timestamp authority;
- institutional backup/recovery;
- independent watchdog/monitoring;
- qualified document repository/eTMF;
- managed-device/MDM services;
- institutional secrets/key management.

These services complement rather than replace ODK, MethodMesh or Sentinel.

---

# 5. ODK project model

## 5.1 Sentinel Control Project

The Control Project is the fleet-level Sentinel registry.

It SHOULD contain or reference:

- registered trials;
- project identifiers;
- Governance Sidecar identifiers;
- approved Sentinel release/schema;
- active/inactive status;
- scheduled-run policy;
- fleet-wide evidence and exceptions.

The Control Project is not a clinical data project.

## 5.2 Study Project

The Study Project contains operational trial data and ordinary ODK lifecycle/history.

It remains the primary data source for study analysis and operational trial work.

## 5.3 Governance Sidecar Project

The Governance Sidecar is the restricted append-oriented evidence project for the trial.

It contains or references evidence such as:

- approved trial design;
- roles and responsibilities;
- access declarations and discrepancies;
- form releases and deployment state;
- compiler task events;
- controlled-document index;
- credential/public-key governance;
- MethodMesh verification results;
- query/deviation histories;
- Sentinel run events;
- cryptographic manifests and attestations;
- lock/archive events.

Ordinary trial staff SHOULD NOT require routine write access to the Sidecar.

---

# 6. The Sentinel task model

## 6.1 Rationale

The future GUI, CLI and VM service MUST NOT contain separate implementations of the same regulated action.

A regulated operation is therefore represented as a **Sentinel task**.

The first implemented task is:

```text
task_type: form.compile
task_schema_version: 1
event_schema: methodmesh.sentinel.task_event.v1
```

## 6.2 Generic task lifecycle

A task has a stable request identity and produces a durable event/receipt.

Conceptually:

```text
REQUEST
  request_id
  task_type
  task_schema_version
  request_source
  authenticated operator (when available)
  trial/study context
  input identities + hashes
  parameters

EXECUTION
  started_at
  completed_at
  monotonic duration where available
  implementation identity/version/fingerprint
  warnings
  diagnostics

RESULT
  status
  output identities
  output hashes
  governed artefacts
  error information if failed
```

A task failure is itself governance evidence and MUST NOT disappear merely because the intended operation did not complete.

## 6.3 Desktop-to-VM rule

For regulated use, the intended flow is:

```text
Desktop
   │
   │ authenticated task request
   ▼
Sentinel Service / VM
   │
   ├── authorise
   ├── execute task engine
   ├── persist/request Sidecar evidence
   └── return task result
```

The Desktop SHOULD NOT directly write Governance Sidecar records using its own independent logic.

## 6.4 Sidecar logging invariant

Every governed action initiated through Sentinel Desktop MUST produce a Sidecar-reconcilable event.

The exact two-phase persistence protocol remains **PLANNED**, but the architecture MUST ensure that:

- a task has a stable request ID before execution;
- success and failure are both recordable;
- output hashes/identities are stable;
- Sidecar ingestion is idempotent;
- an action cannot be represented as governed/closed if its audit event is silently lost.

For tasks that can produce a useful local artefact while ODK Central is unavailable, the resulting artefact SHOULD remain explicitly **unregistered/pending governance** until the task receipt has been ingested and reconciled with the Sidecar.

---

# 7. MethodMesh XLSForm Compiler

**Implementation state:** IMPLEMENTED; qualification and deployment integration remain.

## 7.1 Role

The compiler is the first Sentinel task engine.

It turns an ordinary ODK XLSForm into a MethodMesh-authenticated and attested release form while preserving the principle that form authors work primarily with normal XLSForm semantics.

The compiler is not a throwaway build script. It is part of the governed release pipeline.

## 7.2 Architecture

```text
Sentinel task wrapper
       │
       └── run_form_compile_task(...)
               │
               ▼
       deterministic transformer
       compile_xlsform(...)
```

The CLI calls the Sentinel task wrapper.

The future Desktop and VM service SHOULD call the same task contract rather than duplicating compiler behaviour.

## 7.3 Authoring surface

The supported authoring controls include:

### `mm_commit` survey column

Accepted values:

| Value | Meaning |
|---|---|
| blank / `auto` | compiler selects the supported safe default |
| `value` | commit canonical scalar value |
| `sha256` | commit SHA-256 of the ODK lexical string |
| `exclude` | submit normally but exclude from attested commitment |

The compiler is deliberately fail-closed where it cannot construct a deterministic supported commitment.

### `methodmesh` sheet

Typical keys include:

```text
enabled
study_id
description
authentication
timestamp_policy
```

Trial/study identity belongs in explicit governed configuration, not inferred from filenames.

## 7.4 Release identity

The compiler owns the deployed ODK release version.

Current format:

```text
YYYYMMDDHHMMSS
```

The same generated value is written into:

- ODK `settings.version`;
- committed `mm_form_version`;
- release filenames/manifests.

Generated releases SHOULD NOT be edited manually. A change requires recompilation from the authoring source.

## 7.5 Immutable release bundle

Every compilation creates a new non-overwriting release directory.

Representative bundle:

```text
<form>__v<version>__build_<timestamp>__<sourcehash>/
    SOURCE__<authoring-form>.xlsx
    <form>__v<version>__methodmesh.xlsx
    MANIFEST.md
    commitment_manifest.json
    BUILD_REPORT.md
    sentinel_task_event.json
    CHECKSUMS.sha256
```

The release directory is the unit of provenance.

Good provenance starts before deployment.

## 7.6 Compiler-generated MethodMesh workflow

The compiler currently injects:

- NFC credential + PIN MethodMesh call before protected form UI;
- authentication gate for protected source questions/groups;
- read-only locking after finalisation;
- per-form workflow/form-instance UUID;
- deterministic ordered commitment over governed form context and selected source fields;
- `methodmesh.commitment_recipe.v1`;
- frozen SHA-256 commitment using `once(...)`;
- live reconstruction check against the frozen hash;
- `attestation.create` reusing the earlier NFC verification execution;
- namespaced authentication and attestation return fields;
- retained FULL MethodMesh JSON evidence;
- `READY TO SUBMIT` calculation;
- final guard preventing completion unless live data, frozen ODK commitment and returned MethodMesh attestation reconcile.

## 7.7 Provenance context passed to MethodMesh

The compiler sends only context it genuinely knows:

```text
study_id
form_id
form_version
form_instance_id
```

The compiler-generated workflow UUID is a **form instance identifier**.

It MUST NOT be relabelled as `visit_id`.

`visit_id` and `event_id` are absent unless an explicit study mapping supplies them.

For attestation, the compiler also passes:

- the NFC-verified credential subject as requested `operator_id`;
- the prior NFC verification execution ID.

MethodMesh then independently decides the evidentiary basis of that operator identity.

## 7.8 Compiler task receipt

Successful builds emit:

```text
sentinel_task_event.json
```

The receipt records, at minimum:

- request ID;
- request source;
- optional operator context;
- task type/schema;
- source hash;
- parameters;
- start/completion time;
- monotonic duration;
- compiler semantic version;
- compiler implementation fingerprint;
- status;
- warnings;
- output artefacts and hashes.

Failed builds also emit a machine-readable failure receipt.

## 7.9 Current fail-closed boundaries

Current compiler limitations include:

- repeats must be explicitly excluded;
- binary/media commitment is not yet implemented;
- globally duplicate survey node names are rejected;
- pyxform/ODK validation remains required before deployment.

These are explicit boundaries, not silent omissions.

---

# 8. MethodMesh regulated-trial profile

## 8.1 Purpose

MethodMesh is a general Android capability platform.

For MethodMesh Sentinel, a subset of its infrastructure becomes a regulated-trial assurance layer at the local person/device/action boundary.

The key v1 assurance components are:

- NFC credential verification;
- PIN verification;
- governed credential/issuer evidence;
- common execution provenance;
- Clock Assurance;
- monotonic timing evidence;
- commitment/attestation;
- RFC 3161 trusted timestamp evidence where policy requires;
- future direct instrument/sensor originator evidence where used.

## 8.2 One global envelope, custom capability payloads

MethodMesh capability outputs retain their own module-specific payloads.

The global FULL envelope wraps rather than replaces them.

Conceptually:

```text
methodmesh_full_json
├── global execution envelope
│   ├── application
│   ├── module
│   ├── capability
│   ├── execution_provenance
│   ├── execution_timing
│   └── time_assurance
│
└── capability-specific content
    ├── result/observations
    ├── attestation payload
    ├── NFC evidence
    ├── sensor output
    ├── score
    ├── file/artifact evidence
    └── capability diagnostics
```

This is a critical architecture invariant:

> **Shared provenance envelope; capability-specific scientific/operational payload.**

Sentinel can therefore parse the common envelope generically while using capability-specific parsers only when needed.

---

# 9. MethodMesh FULL envelope v3

**Implementation state:** IMPLEMENTED.

Every canonical FULL MethodMesh result is intended to carry a common schema v3 envelope.

Representative structure:

```json
{
  "methodmesh_envelope_schema_version": "3",
  "application": {
    "application_id": "com.example.methodmesh",
    "version_name": "...",
    "version_code": 0
  },
  "module": {
    "id": "...",
    "version": "...",
    "maturity": "..."
  },
  "capability": {
    "id": "...",
    "version": "...",
    "maturity": "..."
  },
  "execution_provenance": {
    "schema_version": "1",
    "execution_id": "...",
    "method_id": "...",
    "status": "...",
    "caller": "...",
    "record_context": {
      "study_id": "...",
      "site_id": null,
      "visit_id": null,
      "event_id": null,
      "form_id": "...",
      "form_version": "...",
      "form_instance_id": "...",
      "submission_id": null
    },
    "actors": {
      "subject": null,
      "operator": null,
      "data_originator": null
    }
  },
  "execution_timing": {
    "schema_version": "1",
    "started": {},
    "completed": {},
    "continuity": "same_boot",
    "monotonic_duration_ms": 0
  },
  "time_assurance": {
    "schema_version": "1"
  }
}
```

## 9.1 Frozen software identity

Application/module/capability identity is captured as historical execution provenance.

A later application upgrade MUST NOT cause an old execution to claim that a new version produced it.

The envelope records:

- application package ID;
- application version name/code;
- producing module identity/version/maturity;
- producing capability identity/version/maturity.

## 9.2 Structured record context

The standard vocabulary includes, where genuinely known:

```text
study_id
site_id
visit_id
event_id
form_id
form_version
form_instance_id
submission_id
```

Missing provenance is preferable to invented provenance.

## 9.3 Actor model

The envelope distinguishes:

```text
subject
operator
data_originator
```

These MUST NOT be conflated.

Examples:

- staff enters a CRF: staff may be operator and data originator; participant is subject;
- connected scale: participant is subject, nurse is operator, scale/instrument is data originator;
- MethodMesh calculates a score: subject may be participant; MethodMesh capability is data originator;
- participant completes a PRO: participant is data originator and subject.

Each actor identity retains an **assertion basis**.

---

# 10. Identity, attribution and assertion basis

## 10.1 Request context is a claim

An ODK/intent/RIL caller may supply:

```text
operator_id = g
```

That fact alone establishes only:

```text
assertion_basis = request_context
```

The global envelope MUST NOT silently upgrade this to authenticated identity.

## 10.2 NFC credential verification

The standard current staff assurance profile uses:

- NFC credential;
- credential signature verification;
- PIN verification;
- credential subject identifier;
- issuer key identifier;
- issuer trust evaluation state;
- MethodMesh execution ID.

The successful verification execution becomes reusable evidence for the subsequent attestation within the same governed form context.

## 10.3 Form-instance binding for verification reuse

Reusing an NFC credential verification for attestation requires matching governed context.

The required binding is:

```text
caller
study_id
form_id
form_version
form_instance_id
```

`visit_id` and `event_id` are optional contextual checks. If they are present on both executions, they must agree. They are not required merely to reuse verification.

This prevents a credential verification from one form instance being silently replayed into another.

## 10.4 Authenticated operator reconciliation

For `attestation.create`, MethodMesh resolves the prior NFC verification internally.

If the caller supplied `operator_id`, MethodMesh compares it with the authenticated credential subject.

If they differ, attestation fails.

If they agree, the authenticated subject becomes the effective attestation operator.

## 10.5 Stronger operator provenance

The global envelope may promote the operator assertion only when the successful capability result contains evidence supporting that promotion.

For the current NFC+PIN attestation path:

```text
request_context
      │
      │ referenced successful NFC verification
      ▼
nfc_credential_pin_signature_verified
```

Where the credential issuer is also checked against the governed trusted issuer set, the stronger basis may be:

```text
trusted_nfc_credential
```

The envelope should retain assertion evidence such as:

```text
source_execution_id
source_method_id
evidence_format
evidence_hash
issuer_key_id
issuer_trust_status
```

This distinction is intentional.

A cryptographically valid credential whose issuer trust was `not_checked` MUST NOT be represented as a fully governed/trusted trial credential.

---

# 11. Clock Assurance and temporal provenance

**Implementation state:** shared envelope/monotonic evidence IMPLEMENTED; final deployment policy and qualification remain.

## 11.1 Universal evidence

Every FULL execution envelope carries `time_assurance`.

Clock evidence is global execution infrastructure, not a special property of attestation.

## 11.2 Wall clock is not enough

The platform does not treat the device wall clock as authoritative merely because Android reported it.

The common evidence may include:

- observed wall time;
- trusted-time estimate;
- lower/upper trusted bounds;
- uncertainty;
- trusted anchor source;
- anchor evidence commitment;
- anchor age;
- wall-clock relation to trusted interval;
- boot/session identity;
- monotonic elapsed time.

## 11.3 Request-to-completion monotonic timing

The shared execution engine captures:

- a lightweight request boundary;
- the completion Clock Assurance snapshot.

`monotonic_duration_ms` is emitted only where both boundaries are demonstrably in the same boot session and the monotonic reading is coherent.

Reboot, unavailable boot identity or regression MUST be explicit.

Duration MUST NOT be fabricated from wall-clock subtraction.

## 11.4 Trusted timestamp is not the same as trusted current time

RFC 3161 timestamp evidence answers:

> When did these exact bytes/hash demonstrably exist according to the TSA?

Clock Assurance answers:

> What evidence do we have about the device's current-time estimate when this execution occurred?

A timestamp token does not automatically become a shared clock anchor merely because its internal signature is valid.

---

# 12. Attestation and exact-object commitment

**Implementation state:** IMPLEMENTED / QUALIFY.

## 12.1 Responsibility split

ODK owns construction of the governed form commitment.

MethodMesh owns validation and attestation of that exact commitment.

Sentinel independently verifies it later.

```text
ODK constructs canonical commitment
        │
        ▼
ODK computes SHA-256
        │
        ▼
MethodMesh receives:
    event_payload_hash
    commitment_recipe
    verification method/evidence
    governed context
    timestamp policy
        │
        ▼
MethodMesh validates + signs/attests
        │
        ▼
ODK retains attestation + FULL envelope
        │
        ▼
Sentinel reconstructs independently
```

## 12.2 Commitment recipe

Current recipe schema:

```text
methodmesh.commitment_recipe.v1
```

Canonicalization:

```text
ordered-kv-v1
```

Hash:

```text
SHA-256
```

The recipe is declarative.

It MUST NOT execute arbitrary expressions, XPath, JavaScript or ODK calculations as code.

## 12.3 Exact-object binding

The signed attestation binds:

- `event_payload_hash`;
- hash/identity of the commitment recipe;
- operator/verification evidence;
- event/action context;
- MethodMesh execution/software provenance;
- temporal evidence;
- timestamp evidence according to policy.

Large objects should be represented through explicit byte hashes rather than copied wholesale through the attestation API.

## 12.4 Timestamp policy

Supported policy model:

```text
disabled
preferred
required
```

If trusted timestamping is required and unavailable, the attestation MUST fail rather than silently downgrade the claim.

---

# 13. Regulated staff form-submission assurance

The standard v1 trial profile may require one MethodMesh assurance chain for each completed regulated staff submission or re-submission.

This is submission/form-instance assurance, not per-field re-authentication.

## 13.1 Expected flow

```text
1. ODK opens generated trial form
2. MethodMesh verifies NFC credential + PIN
3. ODK stores verification execution ID and FULL evidence
4. user completes protected form content
5. ODK constructs deterministic commitment
6. ODK freezes commitment hash
7. ODK calls attestation.create
8. MethodMesh resolves/reuses prior NFC verification
9. MethodMesh verifies same governed form-instance context
10. MethodMesh reconciles requested operator with authenticated credential subject
11. MethodMesh signs/attests exact commitment
12. trusted timestamp evidence obtained/verified according to policy
13. ODK checks returned attested hash == frozen ODK hash
14. READY TO SUBMIT becomes true only when the complete chain reconciles
15. ODK submits
16. Sentinel later re-verifies independently
```

## 13.2 Required form context

At minimum:

```text
study_id
form_id
form_version
form_instance_id
```

Additional site/visit/event/submission identifiers MAY be carried where the instrument genuinely knows them.

## 13.3 ODK remains part of attribution

MethodMesh does not replace ODK account/history attribution.

The assurance layers are complementary:

- ODK Central provides authenticated source-system account/history;
- MethodMesh adds local evidence that the governed credential holder was present and re-authenticated for the protected action;
- Sentinel later reconciles both.

---

# 14. ALCOA+ evidence model

The platform MUST NOT label an execution or system “ALCOA+ compliant” merely because certain metadata fields exist.

The architecture instead identifies evidence relevant to each property.

## 14.1 Attributable

MethodMesh contributes:

- execution ID;
- caller context;
- distinct subject/operator/data-originator roles;
- NFC/PIN credential evidence;
- assertion basis;
- attestation/signing identity.

ODK contributes authenticated account/history.

Sentinel contributes governance reconciliation and credential/key validity checks.

## 14.2 Contemporaneous

MethodMesh contributes:

- observed wall time;
- trusted-time evidence/bounds;
- monotonic request/completion markers;
- boot/session continuity;
- RFC 3161 evidence where applicable.

ODK contributes device/server lifecycle timestamps.

Sentinel contributes later reconciliation and daily attestation chronology.

## 14.3 Original

MethodMesh can commit exact bytes/values/hashes and source identifiers.

ODK remains the source record system.

Whether a particular record is the regulatory original is a workflow and source-system determination, not a label inferred from a hash.

## 14.4 Accurate

Evidence may include:

- validation rules;
- deterministic transformation identity;
- direct device/sensor provenance;
- calibration/configuration evidence;
- cryptographic integrity checks;
- reconciliation outcomes.

Successful execution alone does not establish scientific accuracy.

## 14.5 Legible

Structured machine-readable evidence, human manifests and durable ODK records support later inspection and reconstruction.

## 14.6 Complete, Consistent, Enduring, Available

These are predominantly system-level properties.

They depend on:

- cross-record reconciliation;
- lifecycle/event completeness;
- backup;
- retention;
- archive;
- governed access;
- availability and recovery.

They therefore belong primarily to ODK + Sentinel + repository/archive + institutional controls, not to a single MethodMesh execution.

---

# 15. Sentinel verification responsibility

Sentinel SHOULD independently verify regulated MethodMesh evidence rather than trusting a success flag returned by the field app.

For a staff submission this includes, where applicable:

- MethodMesh envelope schema/version support;
- frozen MethodMesh application/capability identity;
- study/form/version/instance context;
- NFC verification execution identity;
- credential signature evidence;
- PIN verification result;
- issuer identity and governed trust status;
- effective operator identity;
- commitment recipe identity/hash;
- ODK canonical commitment reconstruction;
- ODK payload hash;
- MethodMesh attested payload hash;
- equality of reconstructed/attested commitments;
- MethodMesh attestation signature;
- signing public-key identity and governed registration;
- RFC 3161 evidence according to policy;
- Clock Assurance evidence and trial-specific freshness policy;
- replay/context-binding rules.

Verification outcomes become Governance Sidecar events.

---

# 16. Governance operations in Sentinel Desktop

This section defines the intended operator model. The GUI itself is **PLANNED**.

## 16.1 Forms

The Desktop should make the governed form lifecycle explicit:

```text
Authoring source
    ↓
Compile
    ↓
Validate
    ↓
Approve
    ↓
Deploy
    ↓
Verify deployment
    ↓
Supersede/retire
```

Each transition creates or references a Sentinel task/event.

## 16.2 Roles and responsibilities

The Sidecar should contain the authoritative governed declaration of:

- person;
- trial/site scope;
- role;
- delegated responsibilities;
- effective date;
- expiry/end date where applicable;
- approval evidence;
- supersession/revocation.

A Desktop action such as **Update roles and responsibilities** is a governance task, not merely editing a local spreadsheet.

Sentinel reconciles this declaration against ODK Central assignments and reports discrepancies.

Under the current v1 governance model, access remediation remains a human authorised action unless a future validated release explicitly introduces a privileged automated executor.

## 16.3 Credentials and public keys

The governed register should contain or reference:

- credential holder;
- credential/public-key ID;
- credential type;
- issuer;
- valid-from/valid-until;
- trust status;
- revocation status/reason;
- replacement/supersession;
- provisioning/approval evidence.

Private keys remain outside Sentinel.

## 16.4 Controlled documents

Sentinel should maintain a governed index over controlled documents held in an approved repository:

- identity;
- type;
- version;
- approval/effective state;
- SHA-256;
- repository reference/location;
- supersession;
- required/received status.

Sentinel need not copy all binary documents into ODK if the qualified repository remains authoritative for the binary.

---

# 17. Sentinel runtime model

The original v1 architecture remains the baseline for Sentinel runtime.

## 17.1 Stateless execution

Sentinel SHOULD be reproducible from authoritative external state.

Local caches and work files are conveniences, not the sole evidence store.

## 17.2 Controller/worker model

The runtime should support:

- central discovery/controller;
- per-trial workers;
- per-trial locking;
- incremental processing;
- idempotent writes;
- deterministic task/run identities.

## 17.3 Daily run

The baseline daily run is:

```text
1. discovery
2. source ingestion
3. reconstruction
4. governance evaluation
5. governance write-back
6. reconciliation
7. cryptographic attestation
8. run closure
```

Time-critical safety pathways are separate from this daily cycle.

## 17.4 Daily cryptographic integrity chain

Each completed daily run should:

- build a deterministic manifest of relevant evidence;
- hash the evidence;
- compute an aggregate root;
- link to the previous root;
- obtain external timestamp evidence;
- store the new evidence back in ODK.

The TSA receives a digest, not trial data.

---

# 18. Evidence reconstruction and governance ledgers

The original architecture remains authoritative in principle for the following ledger domains and will be expanded into dedicated chapters in later editions of this Master Book.

## 18.1 Source evidence and record history

Sentinel reconstructs a human-readable record history from the strongest underlying ODK evidence available.

The convenient `record_history` representation is a projection, not the cryptographic root.

## 18.2 Reason for change

Corrections and meaningful edits should be reconcilable with governed reason-for-change evidence where required by trial policy.

## 18.3 Query management

Queries are event histories rather than mutable status rows.

Typical events include:

```text
OPEN
RESPONSE
STATUS_CHANGE
CLOSE
REOPEN
```

Derived current state is a view over those events.

## 18.4 Deviations and violations

Protocol deviation/violation evidence is append-only and reconciled with trial-specific rules.

## 18.5 Access governance

The authoritative roles/responsibilities declaration is compared with actual ODK/project access.

Sentinel detects, records and escalates discrepancies.

## 18.6 Form/document version control

The platform tracks:

- authoring source;
- compiler/release identity;
- approved version;
- deployed ODK version;
- checksums;
- approval/effective state;
- supersession/retirement;
- deployment reconciliation.

---

# 19. Safety, blinding, randomisation and lock

These domains remain part of the inherited v1 architecture but are not all implemented as integrated Sentinel Desktop tasks yet.

## 19.1 Safety notification

Immediate safety/SAE notification MUST NOT wait for the daily Sentinel run.

MethodMesh may provide immediate send-attempt evidence through an appropriate capability such as `sms.send`, while Sentinel later reconciles the safety record and governance trail.

## 19.2 Blinding

Field-level encryption/reveal is a platform control, not the entirety of trial blinding.

Blinding remains a study-specific system/process design.

## 19.3 Randomisation

The platform may record and govern randomisation evidence.

A trial-specific IWRS/randomisation algorithm is not automatically a core Sentinel responsibility.

## 19.4 Database lock/finalisation

Lock is a governed lifecycle event requiring evidence that required preconditions were assessed and the locked evidence set is identifiable and reproducible.

---

# 20. Security model

The platform security model is based on separation of authority and least privilege.

Key principles include:

- separate Sentinel read/write roles where practical;
- ordinary users do not gain Sidecar write authority merely to use study data;
- Desktop does not hold server secrets unnecessarily;
- private signing keys remain local/non-exportable or in approved protected storage;
- Sentinel stores/verifies public trust material rather than users' private keys;
- task authorisation is role-aware;
- credential issuer trust is explicit;
- secrets are not hard-coded into releases;
- external timestamp services receive hashes, not trial data;
- all regulated mutations are reconcilable with governance events.

---

# 21. Backup, archive and availability

The platform must provide controlled recovery independent of the Sentinel VM.

Requirements include:

- ODK Central backup/recovery;
- preservation of Governance Sidecar evidence;
- preservation of governed form release bundles;
- controlled-document repository backup/retention;
- retention of cryptographic trust material required for later verification;
- archival manifests;
- evidence required to reproduce verification after system retirement.

Sentinel is not itself the backup system.

---

# 22. Sentinel software governance

Sentinel itself is regulated infrastructure when used for regulated trial work.

The software lifecycle should therefore retain:

- release identity;
- source-control commit/tag;
- build identity;
- schema versions;
- task-engine versions;
- migration history;
- validation/qualification evidence;
- deployment identity;
- controlled configuration;
- change approvals;
- rollback evidence.

The same principle applies to the MethodMesh Android release and the compiler.

---

# 23. Current implementation baseline

This section separates what has actually been implemented from what is architectural direction.

| Component | State | Current baseline |
|---|---|---|
| MethodMesh Android generic capability platform | IMPLEMENTED | Existing application and capability framework |
| MethodMesh FULL provenance envelope | IMPLEMENTED | Envelope schema v3 |
| Frozen application/module/capability identity | IMPLEMENTED | Included in FULL execution evidence |
| Structured study/form/actor provenance | IMPLEMENTED | `execution_provenance` |
| Subject/operator/data-originator separation | IMPLEMENTED | Global envelope |
| Monotonic request/completion evidence | IMPLEMENTED | `execution_timing` |
| Common Clock Assurance evidence | IMPLEMENTED / QUALIFY | FULL envelope evidence |
| NFC credential + PIN verification | IMPLEMENTED / QUALIFY | Staff assurance profile |
| NFC verification reuse bound to form instance | IMPLEMENTED | Same caller/study/form/version/instance |
| Stronger verified-operator assertion in attestation envelope | IMPLEMENTED | Evidence-derived basis; issuer trust retained |
| Exact commitment + attestation | IMPLEMENTED / QUALIFY | `attestation.create` |
| RFC 3161 timestamp policy/evidence | IMPLEMENTED / QUALIFY | disabled/preferred/required model |
| XLSForm compiler | IMPLEMENTED | v0.3.0 |
| Compiler immutable release bundle | IMPLEMENTED | manifests + checksums + source preservation |
| Sentinel `form.compile` task | IMPLEMENTED | task schema v1 |
| Sentinel Desktop GUI | PLANNED | architecture defined here |
| Sentinel VM/API task service | PLANNED | architecture defined here |
| Automatic Sidecar ingestion for desktop tasks | PLANNED | task receipt provides foundation |
| Role/responsibility GUI/task | PLANNED | Sidecar governance model inherited |
| Form deployment task | PLANNED | controlled lifecycle design |
| Credential-governance GUI/task | PLANNED | register model defined |
| Daily Sentinel governance engine | PILOT / CONTINUE | original architecture retained; qualification required |
| Multi-trial production deployment | PLANNED / QUALIFY | architecture supports it |

---

# 24. Immediate implementation sequence

The recommended near-term sequence is:

## Phase A — finish the ODK ↔ MethodMesh evidence contract

1. freeze/document FULL envelope v3;
2. add regression tests proving common envelope coverage across arbitrary capabilities;
3. retain capability-specific custom payloads;
4. formalise verified-actor assertion basis vocabulary;
5. formalise issuer trust-set configuration;
6. update MethodMesh Master Book regulated sections.

## Phase B — compiler as first complete Sentinel task

1. retain v0.3 task wrapper;
2. add pyxform/ODK Validate integration;
3. define approved validation result in the task event;
4. add trial/Sidecar context to authenticated server execution;
5. ingest `sentinel_task_event.json` into Governance Sidecar;
6. define release approval/deployment state.

## Phase C — Sentinel Service

1. define service authentication;
2. define role/authorisation model;
3. expose task API;
4. execute `form.compile`;
5. write task events to Sidecar;
6. implement idempotency/retry/reconciliation;
7. expose task status/history.

## Phase D — Sentinel Desktop

1. task browser/history;
2. Compile Form;
3. release inspection;
4. form validation/deployment;
5. roles/responsibilities editor;
6. access-discrepancy review;
7. credential/public-key governance;
8. run/verification status.

The GUI should follow the service/task model, not precede it.

---

# 25. Acceptance principles for the first integrated proof of principle

The first integrated MethodMesh Sentinel proof of principle should demonstrate that:

1. an ordinary source XLSForm can be transformed by the governed compiler;
2. the release is uniquely identified and immutable;
3. the compiler execution itself has a Sentinel task receipt;
4. an ODK form instance invokes MethodMesh NFC+PIN verification;
5. the exact same governed form instance is bound to later attestation;
6. the authenticated credential subject is reconciled with the attestation operator;
7. the FULL envelope records software, record, actor and time provenance;
8. caller-declared identity is distinguishable from stronger authenticated identity;
9. ODK constructs and freezes the exact payload commitment;
10. MethodMesh attests that commitment rather than receiving an uncontrolled raw-form dump;
11. the attested hash matches the frozen ODK commitment before submission;
12. trusted timestamp policy behaves fail-closed where required;
13. the submitted ODK record preserves the MethodMesh evidence;
14. Sentinel can independently reconstruct and verify the complete chain;
15. the verification outcome is written to the Governance Sidecar;
16. a Desktop-originated governed task can be shown to have traversed the Sentinel Service and produced an append-only Sidecar event.

Items 1–13 are substantially represented by the current compiler/MethodMesh implementation and test workflow. Items 14–16 define the next integration boundary.

---

# 26. Architectural claims inherited from the original v1 plan

The following claims remain foundational:

1. ODK remains the authoritative operational data system.
2. Sentinel is a governance/reconciliation layer, not a shadow clinical database.
3. Governance Sidecar evidence is separated from ordinary study operations.
4. Sentinel is generic and multi-trial.
5. Governance evidence is append-only.
6. Daily cryptographic chaining provides an integrity proof across reconciled evidence.
7. Field assurance remains offline-capable.
8. MethodMesh capabilities remain generic.
9. Native ODK audit evidence and Sentinel audit projections are distinct.
10. Time-critical pathways such as safety notification are not deferred to the daily run.
11. Field-level encryption is only one component of blinding.
12. Study-specific systems such as IWRS may remain external.
13. Originator assurance is layered and risk-proportionate.
14. MethodMesh assurance is broader than electronic signature.
15. Staff assurance can be submission-scoped rather than per-field.
16. Participant PRO assurance need not require MethodMesh on the participant's device.
17. Long-term completeness/availability/retention remain platform/institutional responsibilities rather than properties of one mobile execution.

---

# 27. Chapters to be expanded from the original architecture

The original v1 plan contains detailed designs that remain part of the MethodMesh Sentinel programme and should be absorbed into later editions of this Master Book rather than maintained indefinitely as a separate competing architecture document.

The next consolidation pass should expand dedicated chapters for:

- trial registry and automatic discovery;
- trial-design YAML/schema governance;
- source-evidence reconstruction;
- reason-for-change workflow;
- query management;
- deviations/violations;
- user-access governance;
- controlled documents and form deployment;
- participant PRO originator assurance;
- safety/SAE governance;
- blinding and controlled reveal;
- randomisation interfaces;
- database lock;
- daily cryptographic root/TSA chain;
- backup/disaster recovery;
- watchdog and failure monitoring;
- Sentinel software governance and validation;
- security threat model;
- TMF/eTMF and archive package;
- performance/scale;
- pilot qualification and formal acceptance criteria.

The aim is a single coherent authority, not a growing set of partially overlapping specifications.

---

# 28. Open architectural decisions

The following are intentionally not settled by this foundation draft:

1. Desktop implementation technology and packaging.
2. Sentinel Service API transport and authentication mechanism.
3. Whether task `REQUESTED` events are always committed to Sidecar before execution or whether certain local-transform tasks may enter a `PENDING_LEDGER` state.
4. Exact ODK forms/schemas used to persist generic task events.
5. Formal role model for Desktop task authorisation.
6. Credential issuer provisioning/revocation operations.
7. Production trusted-time source and managed-device policy.
8. Long-term cryptographic key/certificate archival policy.
9. Production document repository connector.
10. Deployment-specific investigator/site certified-copy process.
11. Final interface between Sentinel and institutional eTMF.
12. Formal validation package structure for MHRA-regulated deployment.

These are bounded design tasks. They do not require changing the fundamental three-layer architecture of ODK + MethodMesh + Sentinel.

---

# 29. Summary architecture

MethodMesh Sentinel is therefore:

```text
AUTHOR
  │
  │ ordinary governed XLSForm
  ▼
SENTINEL TASK ENGINE
  form.compile
  │
  ├── source preservation
  ├── deterministic MethodMesh integration
  ├── release identity
  ├── commitment manifest
  ├── human manifest
  ├── task receipt
  └── checksums
  │
  ▼
GOVERNED ODK RELEASE
  │
  ▼
ODK COLLECT  ↔  METHODMESH
  │              │
  │              ├── NFC + PIN
  │              ├── common provenance envelope
  │              ├── Clock Assurance
  │              ├── monotonic execution timing
  │              └── exact commitment attestation
  │
  ▼
ODK CENTRAL
  ├── Study Project
  └── Governance Sidecar
          ▲
          │
          │ governed tasks / verification / reconciliation
          │
SENTINEL SERVICE ON CONTROLLED VM
          ▲
          │
          │ authenticated operator requests
          │
METHODMESH SENTINEL DESKTOP
```

The defining design rule is:

> **Keep the scientific/operational record in ODK; generate local assurance at the person/device boundary in MethodMesh; execute governance through Sentinel; and preserve the evidence durably in the Governance Sidecar.**

---

# Appendix A — Current canonical identifiers

## A.1 MethodMesh

```text
methodmesh_envelope_schema_version = 3
```

Common regulated context:

```text
study_id
site_id
visit_id
event_id
form_id
form_version
form_instance_id
submission_id
subject_id / context_entity_id
operator_id
data_originator_type
data_originator_id
caller
```

## A.2 Compiler

```text
compiler release: 0.3.0
task event schema: methodmesh.sentinel.task_event.v1
task type: form.compile
task schema version: 1
commitment recipe: methodmesh.commitment_recipe.v1
ODK release version: YYYYMMDDHHMMSS
```

## A.3 Assertion basis vocabulary — current/provisional

```text
request_context
nfc_credential_pin_signature_verified
trusted_nfc_credential
```

This vocabulary should become an explicit versioned shared contract before production qualification.

---

# Appendix B — Documentation consolidation rule

This Master Book is intended to become the architecture source of truth for MethodMesh Sentinel.

Once sections of the original trial-platform specification have been fully absorbed and reviewed here, the old document should be retained as historical provenance rather than maintained as an independent current architecture authority.

Likewise, regulated MethodMesh-specific rules should be referenced consistently between this book and the MethodMesh Master Book so that one component does not silently drift away from the cross-system contract.
