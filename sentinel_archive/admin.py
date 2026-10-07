"""Privileged, manually initiated monthly Central administration snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .central import CentralError
from .crawler import (_audit_xml, _json_document_pdf, _sha, snapshot_attachment_fields,
                      snapshot_attachment_names)
from .project import audit_instance_id


ADMIN_ACTIONS = {
    "user.create", "user.update", "user.delete", "user.session.create",
    "user.assignment.create", "user.assignment.delete", "project.create",
    "project.update", "project.delete", "form.create", "form.update",
    "form.update.draft.set", "form.update.draft.delete", "form.update.publish",
    "form.update.draft.replace", "form.delete", "form.restore", "form.purge",
    "field_key.create", "field_key.assignment.create", "field_key.assignment.delete",
    "field_key.session.end", "field_key.delete", "public_link.create",
    "public_link.assignment.create", "public_link.assignment.delete",
    "public_link.session.end", "public_link.delete", "config.set", "upgrade.server",
}


def run_admin_validation(client: Any, output_dir: str | Path) -> dict[str, Any]:
    """Collect a privileged, time-scoped server/project administration snapshot."""
    config = client.config
    run_id = "admin-" + uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)
    start = getattr(config, "admin_audit_start", "") or (now - timedelta(days=31)).isoformat().replace("+00:00", "Z")
    end = getattr(config, "admin_audit_end", "") or now.isoformat().replace("+00:00", "Z")
    project_ids = tuple(str(value) for value in getattr(config, "admin_project_ids", ())
                        ) or (str(config.project_id),)
    checks: list[dict[str, str]] = []
    raw: dict[str, Any] = {}

    def add(check_id: str, passed: bool, detail: str, *, warning: bool = False) -> None:
        status = "pass" if passed else ("warning" if warning else "fail")
        checks.append({
            "check_id": check_id,
            "component": "ODK Central",
            "mode": "privileged_manual_run",
            "status": status,
            "detail": detail,
            "evidence_ref": "",
        })

    try:
        current_user = client.user("current") or {}
        raw["central/current_user.json"] = current_user
        add("admin_current_user", bool(current_user), "Authenticated administrator identity was readable")
    except CentralError as error:
        current_user = {}
        add("admin_current_user", False, f"Could not read authenticated administrator: {type(error).__name__}")

    try:
        projects = client.projects()
        raw["central/projects.json"] = projects
        visible_ids = {str(item.get("id")) for item in projects}
        missing = sorted(set(project_ids) - visible_ids)
        add("admin_project_scope", not missing,
            f"Configured project scope resolved: {len(project_ids)} project(s)"
            if not missing else f"Configured projects not visible to this account: {', '.join(missing)}")
    except CentralError as error:
        projects = []
        visible_ids = set()
        add("admin_project_scope", False, f"Could not list Central projects: {type(error).__name__}")

    assignments_by_project: dict[str, dict[str, list[dict[str, Any]]]] = {}
    actor_ids: set[str] = set()
    for project_id in project_ids:
        assignments_by_project[project_id] = {}
        for role in getattr(config, "admin_assignment_roles", ("manager", "viewer", "dataCollector")):
            try:
                values = client.project_assignments(project_id, str(role))
                assignments_by_project[project_id][str(role)] = values
                for value in values:
                    actor = _actor_id(value)
                    if actor is not None:
                        actor_ids.add(actor)
            except CentralError as error:
                assignments_by_project[project_id][str(role)] = {
                    "error": f"{type(error).__name__}: {error}"
                }
    raw["central/project_assignments.json"] = assignments_by_project
    assignment_errors = [
        project_id + "/" + role
        for project_id, roles in assignments_by_project.items()
        for role, values in roles.items()
        if isinstance(values, dict) and "error" in values
    ]
    add("admin_project_membership", not assignment_errors,
        f"Project user-role assignments read for {len(project_ids)} project(s)"
        if not assignment_errors else f"Could not read assignments: {', '.join(assignment_errors)}")

    try:
        raw["central/roles.json"] = client.roles()
        raw["central/server_assignments.json"] = client.assignments()
        add("admin_server_roles", True, "Server roles and server-wide assignments were readable")
    except CentralError as error:
        add("admin_server_roles", False, f"Could not read server roles/assignments: {type(error).__name__}")

    try:
        server_events = client.server_audits(start=start, end=end)
        raw["central/server_audits.json"] = server_events
        relevant_events = [event for event in server_events if _relevant_event(event, project_ids, actor_ids)]
        raw["central/relevant_audits.json"] = relevant_events
        action_counts: dict[str, int] = {}
        for event in relevant_events:
            action = str(event.get("action") or "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1
        add("admin_server_audit_window", True,
            f"Read {len(server_events)} server audit event(s) in the requested window")
    except CentralError as error:
        server_events = []
        relevant_events = []
        action_counts = {}
        add("admin_server_audit_window", False,
            f"Server audit access failed; Server Administrator permission is required: {type(error).__name__}")

    api_observations: dict[str, Any] = {}
    for key, getter in (("analytics_config", lambda: client.system_config("analytics")),
                        ("analytics_preview", client.analytics_preview)):
        try:
            api_observations[key] = getter()
        except CentralError as error:
            api_observations[key] = {"status": "unavailable", "error": str(error)}
    raw["central/system_observations.json"] = api_observations
    add("admin_system_observations", True, "Available Central system observations were captured")

    host_snapshot = _load_host_snapshot(getattr(config, "admin_host_snapshot_path", ""))
    raw["host/host_snapshot.json"] = host_snapshot
    has_host_metrics = bool(host_snapshot.get("central_version") or host_snapshot.get("uptime_seconds")
                            or host_snapshot.get("disk_space"))
    add("admin_host_metrics", has_host_metrics,
        "Host-side Central version, uptime or disk-space metrics were supplied",
        warning=True)

    status = "failed" if any(check["status"] == "fail" for check in checks) else (
        "passed_with_warnings" if any(check["status"] == "warning" for check in checks) else "passed"
    )
    snapshot = {
        "schema": "methodmesh.sentinel.admin_validation.v1",
        "project_ids": list(project_ids),
        "validation_run_id": run_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "audit_window": {"start": start, "end": end},
        "status": status,
        "checks": checks,
        "summary": {
            "checks": len(checks),
            "passed": sum(check["status"] == "pass" for check in checks),
            "warnings": sum(check["status"] == "warning" for check in checks),
            "failed": sum(check["status"] == "fail" for check in checks),
        },
        "central": {
            "visible_project_count": len(visible_ids),
            "scoped_project_count": len(project_ids),
            "server_audit_events": len(server_events),
            "relevant_audit_events": len(relevant_events),
            "relevant_action_counts": action_counts,
            "project_actor_ids": sorted(actor_ids),
        },
        "host_metrics": host_snapshot,
        "safety": "Read-only administrative observation; no Central data or configuration was changed.",
    }
    raw["admin_snapshot.json"] = snapshot
    for check in snapshot["checks"]:
        check["evidence_ref"] = f"evidence_{run_id}/" + _evidence_for_check(check["check_id"])
    artifacts = _write_admin_artifacts(snapshot, raw, output_dir)
    audit_id = _submit_admin_snapshot(client, snapshot, artifacts)
    return {"snapshot": snapshot, "artifacts": artifacts, "audit_record": audit_id}


def _relevant_event(event: dict[str, Any], project_ids: tuple[str, ...], actor_ids: set[str]) -> bool:
    action = str(event.get("action") or "")
    if action not in ADMIN_ACTIONS:
        return False
    serialized = json.dumps(event, sort_keys=True)
    if any(f'"{project_id}"' in serialized or f"project/{project_id}" in serialized for project_id in project_ids):
        return True
    return _actor_id(event) in actor_ids


def _actor_id(value: Any) -> str | None:
    """Extract the Central audit actor ID across extended-metadata shapes."""
    if not isinstance(value, dict):
        return None
    for key in ("actorId", "actor_id", "actor", "userId", "user_id", "id"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            candidate = candidate.get("id") or candidate.get("userId") or candidate.get("user_id")
        if candidate is not None:
            return str(candidate)
    return None


def _load_host_snapshot(path: str) -> dict[str, Any]:
    if not path:
        return {"status": "not_supplied", "note": "Central API does not expose host uptime or disk space."}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else {"status": "invalid", "error": "Expected JSON object"}
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "unreadable", "error": f"{type(error).__name__}: {error}"}


def _evidence_for_check(check_id: str) -> str:
    if check_id == "admin_current_user":
        return "central/current_user.json"
    if check_id == "admin_server_roles":
        return "central/server_assignments.json"
    if check_id == "admin_project_scope":
        return "central/projects.json"
    if check_id == "admin_project_membership":
        return "central/project_assignments.json"
    if check_id == "admin_server_audit_window":
        return "central/relevant_audits.json"
    if check_id == "admin_host_metrics":
        return "host/host_snapshot.json"
    if check_id == "admin_system_observations":
        return "central/system_observations.json"
    return "admin_snapshot.json"


def _write_admin_artifacts(snapshot: dict[str, Any], raw: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(snapshot["validation_run_id"]))
    evidence_dir = destination / f"evidence_{run_id}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = destination / "admin_snapshot.json"
    json_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pdf_bytes = _json_document_pdf(snapshot, "Sentinel administrator validation snapshot")
    pdf_path = destination / "admin_snapshot.pdf"
    pdf_path.write_bytes(pdf_bytes)
    package_files = [json_path, pdf_path]
    for relative, value in raw.items():
        target = evidence_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            target.write_bytes(value)
        else:
            target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        package_files.append(target)
    manifest = {"schema": "methodmesh.sentinel.admin_evidence_manifest.v1", "files": []}
    for path in package_files:
        manifest["files"].append({"path": str(path.relative_to(destination)), "sha256": _sha(path.read_bytes()),
                                   "size": path.stat().st_size})
    manifest_path = evidence_dir / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    package_files.append(manifest_path)
    package_path = destination / "evidence_package.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_files:
            archive.write(path, path.relative_to(destination))
    return {"json": str(json_path), "pdf": str(pdf_path), "evidence_package": str(package_path)}


def _submit_admin_snapshot(client: Any, snapshot: dict[str, Any], artifacts: dict[str, str]) -> str:
    run_id = str(snapshot["validation_run_id"])
    audit_id = audit_instance_id(str(client.config.project_id), "admin-validation", run_id, run_id)
    snapshot_bytes = Path(artifacts["json"]).read_bytes()
    fields = {
        "record_type": "admin_platform_snapshot",
        "project_id": str(client.config.project_id),
        "source_form_id": "",
        "source_instance_id": "",
        "source_version_id": run_id,
        "source_audit_instance_id": audit_id,
        "source_content_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "central_created_at": snapshot["created_at"],
        "change_reason": "Admin validation snapshot"[:64],
        "reason_link_status": "sentinel_admin_validation",
        "timestamp_status": "not_requested",
        "timestamp_batch_id": run_id,
        "timestamp_batch_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        **snapshot_attachment_fields(
            getattr(client.config, "audit_form_version", "1"),
            "admin_platform_snapshot", "admin_platform_snapshot_pdf",
            "admin_platform_snapshot.json", "admin_platform_snapshot.pdf",
        ),
        "validation_report": "",
        "validation_certificate": "",
        "evidence_package": "evidence_package.zip",
        "sentinel_run_id": run_id,
        "checkpoint_cursor": str(snapshot["summary"]["checks"]),
    }
    json_attachment, pdf_attachment = snapshot_attachment_names(
        fields, "admin_platform_snapshot", "admin_platform_snapshot_pdf")
    attachments = {
        json_attachment: snapshot_bytes,
        pdf_attachment: Path(artifacts["pdf"]).read_bytes(),
        "evidence_package.zip": Path(artifacts["evidence_package"]).read_bytes(),
    }
    client.submit(client.config.audit_form_id,
                  _audit_xml(audit_id, fields, getattr(client.config, "audit_form_version", "1"),
                             client.config.audit_form_id), attachments)
    return audit_id
