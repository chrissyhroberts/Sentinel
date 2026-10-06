"""Read-only, machine-readable validation checks for a configured project run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .crawler import AuditPlan
from .project import audit_instance_id


@dataclass(frozen=True)
class ValidationCheck:
    check_id: str
    component: str
    mode: str
    status: str
    detail: str


def validate_plan(client: Any, plan: AuditPlan) -> dict[str, Any]:
    """Return a JSON-safe validation report without changing Central."""
    config = client.config
    checks: list[ValidationCheck] = []

    def add(check_id: str, component: str, mode: str, passed: bool, detail: str) -> None:
        checks.append(ValidationCheck(check_id, component, mode, "pass" if passed else "fail", detail))

    add("central_project_scope", "ODK Central", "automated", bool(config.project_id),
        f"Project {config.project_id!r} is explicitly configured")
    try:
        project = client.project()
        add("central_project_metadata", "ODK Central", "automated", bool(project.get("id")),
            "Project metadata is readable through the Central API")
    except Exception as error:
        add("central_project_metadata", "ODK Central", "automated", False,
            f"Could not read project metadata: {type(error).__name__}")
    add("central_audit_form", "ODK Central", "automated", bool(config.audit_form_id),
        f"Audit form {config.audit_form_id!r} is configured and was discoverable")
    add("central_source_scope", "ODK Central", "automated", True,
        f"Discovered {len(plan.forms)} source form(s) in the configured project")
    form_ids = [str(form.get("xmlFormId") or form.get("formId") or "") for form in plan.forms]
    add("central_form_ids_unique", "ODK Central", "automated",
        len(form_ids) == len(set(form_ids)), "Visible source form IDs are unique")
    add("central_source_versions", "ODK Central", "automated", True,
        f"Discovered {sum(task[0] == 'form_version' for task in plan.tasks)} form version(s) and "
        f"{sum(task[0] == 'submission_version' for task in plan.tasks)} submission version(s)")
    form_definition_tasks = [task for task in plan.tasks if task[0] == "form_version"]
    try:
        readable = 0
        for _kind, form_id, _logical_id, version_id, _metadata in form_definition_tasks:
            if client.form_version_bytes(form_id, version_id, "xml"):
                readable += 1
        add("central_form_definitions_readable", "ODK Central", "automated",
            readable == len(form_definition_tasks),
            f"Read {readable}/{len(form_definition_tasks)} discovered form definition XML file(s)")
    except Exception as error:
        add("central_form_definitions_readable", "ODK Central", "automated", False,
            f"Could not read a form definition: {type(error).__name__}")

    task_ids = ["\x1f".join((config.project_id, task[1], task[2], task[3])) for task in plan.tasks]
    audit_ids = [audit_instance_id(config.project_id, task[1], task[2], task[3]) for task in plan.tasks]
    add("sentinel_deterministic_ids", "Sentinel", "automated",
        len(audit_ids) == len(set(audit_ids)), "All discovered source tasks have unique deterministic audit IDs")
    add("sentinel_id_length", "Sentinel", "automated",
        all(len(audit_id) <= 64 for audit_id in audit_ids), "Generated audit IDs fit Central's instance ID limit")
    add("sentinel_timestamp_policy", "Sentinel", "automated",
        str(getattr(config, "timestamp_policy", "preferred")).lower() in {"disabled", "preferred", "required"},
        f"Timestamp policy is {getattr(config, 'timestamp_policy', 'preferred')!r}")
    add("sentinel_server_audit_scope", "Sentinel", "automated", True,
        "Server-wide audit collection is enabled" if getattr(config, "server_audit_enabled", False)
        else "Server-wide audit collection is disabled for proportionate project scope")

    try:
        audit_submissions = client.submissions(config.audit_form_id)
        audit_ids = [str(item.get("instanceId") or item.get("id") or "") for item in audit_submissions]
        audit_ids = [value for value in audit_ids if value]
        add("central_audit_read", "ODK Central", "automated", True,
            f"Read {len(audit_ids)} existing audit-form submission(s)")
        add("sentinel_audit_ids_unique", "Sentinel", "automated",
            len(audit_ids) == len(set(audit_ids)), "Existing audit-form instance IDs are unique")
    except Exception as error:  # report a validation failure instead of hiding the permission problem
        add("central_audit_read", "ODK Central", "automated", False,
            f"Could not read audit form: {type(error).__name__}")

    failures = sum(check.status == "fail" for check in checks)
    return {
        "schema": "methodmesh.sentinel.validation_report.v1",
        "project_id": str(config.project_id),
        "components": ["ODK Central", "ODK Collect", "Enketo", "MethodMesh", "Sentinel"],
        "mode": "read_only",
        "status": "failed" if failures else "passed",
        "summary": {"checks": len(checks), "passed": len(checks) - failures, "failed": failures},
        "checks": [asdict(check) for check in checks],
    }


def validation_error(project_id: str, error: Exception) -> dict[str, Any]:
    """Create a report when discovery itself cannot be completed."""
    return {
        "schema": "methodmesh.sentinel.validation_report.v1",
        "project_id": str(project_id),
        "components": ["ODK Central", "ODK Collect", "Enketo", "MethodMesh", "Sentinel"],
        "mode": "read_only",
        "status": "failed",
        "summary": {"checks": 1, "passed": 0, "failed": 1},
        "checks": [{
            "check_id": "central_discovery",
            "component": "ODK Central",
            "mode": "automated",
            "status": "fail",
            "detail": f"Discovery failed: {type(error).__name__}: {error}",
        }],
    }
