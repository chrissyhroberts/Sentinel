from __future__ import annotations

import hashlib
import json
import csv
import io
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Protocol
from xml.sax.saxutils import escape

from .central import CentralClient, CentralError
from .project import audit_instance_id, checkpoint_instance_id
from .timestamp import TimestampError, TimestampEvidence, timestamp_manifest


class AuditSink(Protocol):
    def submit(self, form_id: str, xml: bytes, attachments: dict[str, bytes]) -> None: ...


@dataclass(frozen=True)
class RunSummary:
    project_id: str
    forms_seen: int
    versions_seen: int
    versions_submitted: int
    versions_skipped: int
    form_versions_submitted: int


@dataclass(frozen=True)
class AuditPlan:
    forms: tuple[dict[str, Any], ...]
    tasks: tuple[tuple[str, str, str, str, dict[str, Any]], ...]
    existing_audit_ids: frozenset[str]


class ProjectAuditor:
    """Audit every source form in one configured Central project."""

    def __init__(self, client: CentralClient, sink: AuditSink | None = None):
        self.client = client
        self.sink = sink or client
        self.project_id = client.config.project_id
        self._comment_reasons: dict[tuple[str, str, str], str] = {}

    def plan(self) -> AuditPlan:
        all_forms = self.client.forms()
        deleted_forms = []
        try:
            deleted_forms = self.client.forms(deleted=True)
        except (AttributeError, TypeError):
            pass
        audit_form = self.client.config.audit_form_id
        validation_forms = set(getattr(self.client.config, "validation_form_ids", ()))
        if not any((form.get("xmlFormId") or form.get("formId")) == audit_form for form in all_forms):
            raise RuntimeError(f"Audit form {audit_form!r} was not found in project {self.project_id}")
        forms = tuple(
            form for form in all_forms
            if (form.get("xmlFormId") or form.get("formId")) not in {audit_form, *validation_forms}
        )
        tasks: list[tuple[str, str, str, str, dict[str, Any]]] = []
        for form in forms:
            form_id = str(form.get("xmlFormId") or form.get("formId"))
            for form_version in self.client.form_versions(form_id):
                version_id = str(form_version.get("version") or form_version.get("id") or "")
                if version_id:
                    tasks.append(("form_version", form_id, "form-definition", version_id, form_version))
            for submission in self.client.submissions(form_id):
                logical_id = str(submission.get("instanceId") or submission.get("id") or "")
                if not logical_id:
                    continue
                for version in self.client.versions(form_id, logical_id):
                    version_id = str(version.get("instanceId") or version.get("versionId") or version.get("id") or "")
                    if version_id:
                        tasks.append(("submission_version", form_id, logical_id, version_id, version))
        tasks.extend(self._central_event_tasks(tuple(all_forms) + tuple(deleted_forms), tasks))
        existing = self._existing_audit_ids()
        if hasattr(self.client, "submission"):
            for task in tasks:
                record_id = audit_instance_id(self.project_id, task[1], task[2], task[3])
                if record_id in existing:
                    continue
                try:
                    self.client.submission(audit_form, record_id)
                except CentralError as error:
                    if "returned HTTP 404" not in str(error):
                        raise
                else:
                    existing.add(record_id)
        return AuditPlan(forms, tuple(tasks), frozenset(existing))

    def run(self, plan: AuditPlan | None = None) -> RunSummary:
        plan = plan or self.plan()
        self._prepare_comment_stack(plan)
        run_id = _run_id()
        completed = set(plan.existing_audit_ids)
        forms = plan.forms
        seen = submitted = skipped = form_versions_submitted = 0
        run_records: list[dict[str, Any]] = []
        seen = len(forms)
        for kind, form_id, logical_id, version_id, metadata in plan.tasks:
            record_id = audit_instance_id(self.project_id, form_id, logical_id, version_id)
            if record_id in completed:
                skipped += 1
                run_records.append({
                    "audit_instance_id": record_id,
                    "record_type": "source_form_version" if kind == "form_version" else (
                        "original_submission" if version_id == logical_id else "submission_edit"
                    ) if kind == "submission_version" else metadata.get("record_type", "central_event"),
                    "status": "already_present",
                    "source_form_id": form_id,
                    "source_instance_id": logical_id,
                    "source_version_id": version_id,
                })
                continue
            if getattr(self.client, "debug", False):
                label = f"{form_id}/{version_id}" if kind == "form_version" else f"{form_id}/{logical_id}/{version_id}"
                print(f"[debug] archiving {kind}: {label}", file=sys.stderr)
            try:
                if kind == "form_version":
                    fields = self._submit_form_version(form_id, version_id, metadata, run_id)
                    form_versions_submitted += 1
                elif kind == "submission_version":
                    fields = self._submit_version(form_id, logical_id, version_id, metadata, run_id)
                    submitted += 1
                else:
                    fields = self._submit_central_event(form_id, logical_id, version_id, metadata, run_id)
                    submitted += 1
                run_records.append({
                    "audit_instance_id": record_id,
                    "record_type": fields["record_type"],
                    "status": "submitted",
                    "source_form_id": form_id,
                    "source_instance_id": logical_id,
                    "source_version_id": version_id,
                    "source_content_sha256": fields["source_content_sha256"],
                })
            except CentralError as error:
                if not _is_existing_record(error):
                    raise
                skipped += 1
                run_records.append({
                    "audit_instance_id": record_id,
                    "record_type": "source_form_version" if kind == "form_version" else (
                        "original_submission" if version_id == logical_id else "submission_edit"
                    ) if kind == "submission_version" else metadata.get("record_type", "central_event"),
                    "status": "already_present",
                    "source_form_id": form_id,
                    "source_instance_id": logical_id,
                    "source_version_id": version_id,
                })
                if getattr(self.client, "debug", False):
                    print("[debug] Central already has this audit record; continuing", file=sys.stderr)
        snapshot_fields, snapshot_attachments = self._submit_platform_snapshot(plan, run_id, submit=False)
        users_fields, users_attachments = self._submit_user_roles_snapshot(run_id, submit=False)
        checkpoint_id = checkpoint_instance_id(self.project_id)
        if checkpoint_id not in completed:
            self._submit_checkpoint(forms_seen=seen, versions_seen=submitted + skipped, run_id=run_id)
        previous = self._previous_manifest_reference()
        manifest_fields, manifest_attachments = self._submit_run_manifest(run_id, run_records, previous, submit=False)
        validation_fields, validation_attachments = self._submit_validation_certificate(
            run_id, plan, run_records, previous, manifest_fields, submit=False)
        for key in ("project_health_snapshot", "project_health_snapshot_pdf",
                    "project_user_roles_snapshot", "project_user_roles_snapshot_pdf"):
            if snapshot_fields.get(key):
                manifest_fields[key] = snapshot_fields[key]
            if users_fields.get(key):
                manifest_fields[key] = users_fields[key]
        for key in ("validation_report", "validation_certificate", "evidence_package"):
            if validation_fields.get(key):
                manifest_fields[key] = validation_fields[key]
        manifest_attachments.update(snapshot_attachments)
        manifest_attachments.update(users_attachments)
        for filename in ("validation_report.json", "validation_certificate.pdf", "evidence_package.zip"):
            if filename in validation_attachments:
                manifest_attachments[filename] = validation_attachments[filename]
        self.sink.submit(
            self.client.config.audit_form_id,
            _audit_xml(run_manifest_instance_id(self.project_id, run_id), manifest_fields,
                       getattr(self.client.config, "audit_form_version", "1"),
                       self.client.config.audit_form_id),
            manifest_attachments,
        )
        return RunSummary(self.project_id, seen, submitted + skipped, submitted, skipped, form_versions_submitted)

    def _central_event_tasks(self, forms: tuple[dict[str, Any], ...], source_tasks: list[tuple]) -> list[tuple]:
        if not getattr(self.client.config, "server_audit_enabled", False):
            return []
        getter = getattr(self.client, "server_audits", None)
        if getter is None:
            return []
        start = self._server_audit_start()
        events = getter(start=start) if start else getter()
        audit_form = self.client.config.audit_form_id
        form_ids = {
            str(form.get("xmlFormId") or form.get("formId") or "")
            for form in forms
            if (form.get("xmlFormId") or form.get("formId")) != audit_form
        }
        form_ids -= set(getattr(self.client.config, "validation_form_ids", ()))
        form_ids.discard("")
        form_numeric_ids = {str(form.get("id")) for form in forms if form.get("id") is not None}
        submission_ids = {task[2] for task in source_tasks if task[0] == "submission_version"}
        actor_ids = {
            str(task[4].get("actorId") or task[4].get("submitterId"))
            for task in source_tasks if task[0] == "submission_version"
            and (task[4].get("actorId") or task[4].get("submitterId")) is not None
        }
        tasks: list[tuple] = []
        for event in events:
            action = str(event.get("action") or "")
            if not _central_action_is_relevant(action):
                continue
            if not _central_event_in_project(event, self.project_id, form_ids, form_numeric_ids,
                                              submission_ids, actor_ids):
                continue
            event_key = _central_event_key(event)
            metadata = {
                "record_type": _central_record_type(action),
                "project_id": self.project_id,
                "event": event,
            }
            tasks.append(("central_event", "central-event", event_key, event_key, metadata))
        return tasks

    def _submit_platform_snapshot(self, plan: AuditPlan, run_id: str, *, submit: bool = True):
        project_status = "available"
        project_metadata: dict[str, Any] = {}
        try:
            project_metadata = self.client.project()
        except (AttributeError, CentralError) as error:
            project_status = f"unavailable: {type(error).__name__}"
        forms: list[dict[str, Any]] = []
        retained_versions_by_form: dict[str, int] = {}
        for kind, form_id, _logical_id, _version_id, _metadata in plan.tasks:
            if kind == "submission_version":
                retained_versions_by_form[form_id] = retained_versions_by_form.get(form_id, 0) + 1
        for form in plan.forms:
            form_id = str(form.get("xmlFormId") or form.get("formId") or "")
            versions = self.client.form_versions(form_id)
            submissions = self.client.submissions(form_id)
            dates = [str(item.get("createdAt") or item.get("created_at")) for item in submissions
                     if item.get("createdAt") or item.get("created_at")]
            forms.append({
                "form_id": form_id,
                "form_state": form.get("state", ""),
                "published_versions": len(versions),
                "submissions": len(submissions),
                "retained_versions": retained_versions_by_form.get(form_id, 0),
                "latest_submission_at": max(dates) if dates else "",
            })
        snapshot = {
            "schema": "methodmesh.sentinel.project_health_snapshot.v1",
            "project_id": self.project_id,
            "run_id": run_id,
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_api_status": project_status,
            "project_metadata": {
                key: project_metadata.get(key)
                for key in ("id", "name", "createdAt", "updatedAt", "archived")
                if key in project_metadata
            },
            "audit_form_id": self.client.config.audit_form_id,
            "audit_form_version": getattr(self.client.config, "audit_form_version", "1"),
            "source_forms": forms,
            "source_form_count": len(forms),
            "planned_source_records": len(plan.tasks),
            "server_audit_enabled": bool(getattr(self.client.config, "server_audit_enabled", False)),
        }
        snapshot_bytes = (json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        snapshot_pdf = _json_document_pdf(snapshot, "Sentinel project health snapshot")
        audit_id = audit_instance_id(self.project_id, "project-health", run_id, run_id)
        fields = {
            "record_type": "project_health_snapshot",
            "project_id": self.project_id,
            "source_form_id": "",
            "source_instance_id": "",
            "source_version_id": run_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(snapshot_bytes),
            "collect_audit_sha256": "",
            "central_created_at": snapshot["observed_at"],
            "central_actor_id": "",
            "change_reason": "Project health snapshot",
            "reason_link_status": "sentinel_platform_observation",
            "timestamp_status": "covered_by_run_manifest",
            "timestamp_time": "",
            "timestamp_batch_id": run_id,
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            **snapshot_attachment_fields(
                getattr(self.client.config, "audit_form_version", "1"),
                "project_health_snapshot", "project_health_snapshot_pdf",
                "project_health_snapshot.json", "project_health_snapshot.pdf" if snapshot_pdf else "",
            ),
            "validation_report": "",
            "validation_certificate": "",
            "evidence_package": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": str(len(plan.tasks)),
        }
        json_attachment, pdf_attachment = snapshot_attachment_names(
            fields, "project_health_snapshot", "project_health_snapshot_pdf")
        snapshot_attachments = {json_attachment: snapshot_bytes}
        if snapshot_pdf:
            snapshot_attachments[pdf_attachment] = snapshot_pdf
        if submit:
            self.sink.submit(
                self.client.config.audit_form_id,
                _audit_xml(audit_id, fields, getattr(self.client.config, "audit_form_version", "1"),
                           self.client.config.audit_form_id),
                snapshot_attachments,
            )
        return fields, snapshot_attachments

    def _submit_user_roles_snapshot(self, run_id: str, *, submit: bool = True):
        inventory = self._project_user_inventory()
        snapshot = {
            "schema": "methodmesh.sentinel.project_user_roles_snapshot.v1",
            "project_id": self.project_id,
            "run_id": run_id,
            "observed_at": inventory["observed_at"],
            "inventory": inventory,
            "safety": "Project-visible user and role metadata only; no source data copied.",
        }
        snapshot_bytes = (json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        snapshot_pdf = _json_document_pdf(snapshot, "Sentinel project user and role snapshot")
        audit_id = audit_instance_id(self.project_id, "project-users", run_id, run_id)
        fields = {
            "record_type": "project_user_roles_snapshot",
            "project_id": self.project_id,
            "source_form_id": "",
            "source_instance_id": "",
            "source_version_id": run_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(snapshot_bytes),
            "collect_audit_sha256": "",
            "central_created_at": snapshot["observed_at"],
            "central_actor_id": "",
            "change_reason": "Project user and role snapshot",
            "reason_link_status": "sentinel_project_observation",
            "timestamp_status": "covered_by_run_manifest",
            "timestamp_time": "",
            "timestamp_batch_id": run_id,
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            **snapshot_attachment_fields(
                getattr(self.client.config, "audit_form_version", "1"),
                "project_user_roles_snapshot", "project_user_roles_snapshot_pdf",
                "project_user_roles_snapshot.json", "project_user_roles_snapshot.pdf" if snapshot_pdf else "",
            ),
            "validation_report": "",
            "validation_certificate": "",
            "evidence_package": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": "",
        }
        json_attachment, pdf_attachment = snapshot_attachment_names(
            fields, "project_user_roles_snapshot", "project_user_roles_snapshot_pdf")
        attachments = {json_attachment: snapshot_bytes}
        if snapshot_pdf:
            attachments[pdf_attachment] = snapshot_pdf
        if submit:
            self.sink.submit(
                self.client.config.audit_form_id,
                _audit_xml(audit_id, fields, getattr(self.client.config, "audit_form_version", "1"),
                           self.client.config.audit_form_id),
                attachments,
            )
        return fields, attachments

    def _project_user_inventory(self) -> dict[str, Any]:
        """Capture the regular account's current project users and roles."""
        inventory: dict[str, Any] = {
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": self.project_id,
            "web_users": {"status": "unavailable", "items": []},
            "app_users": {"status": "unavailable", "items": []},
            "roles": {"status": "unavailable", "items": []},
            "project_assignments": {},
            "current_project_users": [],
            "login_observation": {
                "status": "unavailable_without_server_audit_access",
                "note": "Web User last-login dates require the privileged Central audit feed.",
            },
        }
        try:
            inventory["web_users"] = {"status": "available", "items": self.client.users()}
        except (AttributeError, CentralError) as error:
            inventory["web_users"] = {"status": "unavailable", "error": type(error).__name__, "items": []}
        try:
            roles = self.client.roles()
            inventory["roles"] = {"status": "available", "items": roles}
        except (AttributeError, CentralError) as error:
            roles = []
            inventory["roles"] = {"status": "unavailable", "error": type(error).__name__, "items": []}
        role_keys: list[str] = []
        for role in roles:
            key = role.get("system") or role.get("id") or role.get("name")
            if key is not None:
                role_keys.append(str(key))
        for role_key in role_keys:
            try:
                inventory["project_assignments"][role_key] = {
                    "status": "available",
                    "items": self.client.project_assignments(self.project_id, role_key),
                }
            except (AttributeError, CentralError) as error:
                inventory["project_assignments"][role_key] = {
                    "status": "unavailable", "error": type(error).__name__, "items": [],
                }
        try:
            inventory["app_users"] = {"status": "available", "items": self.client.app_users(self.project_id)}
        except (AttributeError, CentralError) as error:
            inventory["app_users"] = {"status": "unavailable", "error": type(error).__name__, "items": []}

        web_users = inventory["web_users"].get("items", [])
        web_by_id = {str(item.get("id")): item for item in web_users if item.get("id") is not None}
        members: dict[str, dict[str, Any]] = {}
        for role_key, assignment in inventory["project_assignments"].items():
            if not isinstance(assignment, dict):
                continue
            for value in assignment.get("items", []):
                if not isinstance(value, dict):
                    continue
                actor = value.get("actor") if isinstance(value.get("actor"), dict) else value
                actor_id = actor.get("id") or value.get("actorId") or value.get("actor_id")
                if actor_id is None:
                    continue
                actor_id = str(actor_id)
                source = dict(web_by_id.get(actor_id, {}))
                source.update(actor)
                member = members.setdefault(actor_id, {
                    "actor_id": actor_id,
                    "display_name": "",
                    "email": "",
                    "actor_type": "",
                    "created_at": "",
                    "updated_at": "",
                    "deleted_at": "",
                    "roles": [],
                    "last_used": "",
                    "last_login": None,
                })
                member.update({
                    "display_name": source.get("displayName") or source.get("display_name") or member["display_name"],
                    "email": source.get("email") or member["email"],
                    "actor_type": source.get("type") or member["actor_type"],
                    "created_at": source.get("createdAt") or member["created_at"],
                    "updated_at": source.get("updatedAt") or member["updated_at"],
                    "deleted_at": source.get("deletedAt") or member["deleted_at"],
                })
                if role_key not in member["roles"]:
                    member["roles"].append(role_key)
        for app_user in inventory["app_users"].get("items", []):
            if not isinstance(app_user, dict):
                continue
            actor = app_user.get("actor") if isinstance(app_user.get("actor"), dict) else app_user
            actor_id = actor.get("id") or app_user.get("id")
            if actor_id is None:
                continue
            actor_id = str(actor_id)
            member = members.setdefault(actor_id, {
                "actor_id": actor_id, "display_name": "", "email": "", "actor_type": "",
                "created_at": "", "updated_at": "", "deleted_at": "", "roles": [],
                "last_used": "", "last_login": None,
            })
            member.update({
                "display_name": actor.get("displayName") or actor.get("display_name") or member["display_name"],
                "actor_type": actor.get("type") or "field_key",
                "created_at": actor.get("createdAt") or member["created_at"],
                "updated_at": actor.get("updatedAt") or member["updated_at"],
                "deleted_at": actor.get("deletedAt") or member["deleted_at"],
                "last_used": app_user.get("lastUsed") or app_user.get("last_used") or member["last_used"],
            })
            if "app-user" not in member["roles"]:
                member["roles"].append("app-user")
        for member in members.values():
            member["roles"].sort()
        inventory["current_project_users"] = sorted(
            members.values(), key=lambda item: (item.get("display_name") or "", item["actor_id"])
        )
        return inventory

    def _server_audit_start(self) -> str | None:
        configured = getattr(self.client.config, "server_audit_start", "")
        if configured:
            return str(configured)
        try:
            submissions = self.client.submissions(self.client.config.audit_form_id)
        except CentralError:
            return None
        dates = []
        for submission in submissions:
            value = submission.get("createdAt") or submission.get("created_at")
            parsed = _parse_time(value)
            if parsed:
                dates.append(parsed)
        if not dates:
            return None
        # Small overlap prevents events at the edge of a previous run from
        # being missed. Deterministic event IDs make the overlap harmless.
        return (max(dates) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    def _submit_central_event(self, _form_id: str, event_key: str, _version_id: str,
                              metadata: dict[str, Any], run_id: str) -> dict[str, str]:
        event = metadata["event"]
        action = str(event.get("action") or "")
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        actor_id = event.get("actorId")
        source_form_id = str(details.get("xmlFormId") or details.get("formId") or "")
        source_instance_id = str(details.get("instanceId") or details.get("submissionId") or "")
        event_json = json.dumps(event, sort_keys=True, ensure_ascii=False).encode()
        audit_id = audit_instance_id(self.project_id, "central-event", event_key, event_key)
        fields = {
            "record_type": metadata["record_type"],
            "project_id": self.project_id,
            "source_form_id": source_form_id,
            "source_instance_id": source_instance_id,
            "source_version_id": event_key,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(event_json),
            "collect_audit_sha256": "",
            "central_created_at": str(event.get("loggedAt") or ""),
            "central_actor_id": self._actor_email(actor_id) or str(actor_id or ""),
            "change_reason": _central_event_summary(action, details),
            "reason_link_status": "central_server_audit",
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": event_key,
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(
            audit_id, fields, getattr(self.client.config, "audit_form_version", "1"),
            self.client.config.audit_form_id), {})
        return fields

    def _submit_form_version(self, form_id: str, version_id: str, metadata: dict[str, Any], run_id: str) -> dict[str, str]:
        xml = self.client.form_version_bytes(form_id, version_id, "xml")
        audit_id = audit_instance_id(self.project_id, form_id, "form-definition", version_id)
        fields = {
            "record_type": "source_form_version",
            "project_id": self.project_id,
            "source_form_id": form_id,
            "source_instance_id": "form-definition",
            "source_version_id": version_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(xml),
            "collect_audit_sha256": "",
            "central_created_at": metadata.get("createdAt") or metadata.get("created_at"),
            "central_actor_id": self._actor_email(metadata.get("actorId")) or metadata.get("actorId") or "",
            "change_reason": "",
            "reason_link_status": "not_applicable",
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            "sentinel_run_id": "",
            "checkpoint_cursor": version_id,
        }
        fields["sentinel_run_id"] = run_id
        form_version = getattr(self.client.config, "audit_form_version", "1")
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(
            audit_id, fields, form_version, self.client.config.audit_form_id), {})
        return fields

    def _existing_audit_ids(self) -> set[str]:
        result: set[str] = set()
        for submission in self.client.submissions(self.client.config.audit_form_id):
            value = submission.get("instanceId") or submission.get("id")
            if value:
                result.add(str(value))
        return result

    def _submit_version(self, form_id: str, logical_id: str, version_id: str,
                        version: dict[str, Any], run_id: str) -> dict[str, str]:
        source = self.client.version_xml(form_id, logical_id, version_id)
        audits = self.client.audits(form_id, logical_id)
        diffs = self.client.diffs(form_id, logical_id) if is_edit_candidate(version_id, logical_id) else {}
        collect_audit = _collect_audit_bytes(self.client, form_id, logical_id, version_id)
        audit_id = audit_instance_id(self.project_id, form_id, logical_id, version_id)
        actor_id = version.get("actorId") or version.get("submitterId")
        is_edit = version_id != logical_id
        change_summary = _change_summary(diffs, version_id)
        collect_reason = _collect_reason(collect_audit)
        central_reason = _reason(audits, version_id, version, logical_id)
        comment_reason = self._comment_reasons.get((form_id, logical_id, version_id), "")
        reason = _combine_reason(change_summary, collect_reason or central_reason or comment_reason)
        metadata = {
            "record_type": "submission_edit" if is_edit else "original_submission",
            "project_id": self.project_id,
            "source_form_id": form_id,
            "source_instance_id": logical_id,
            "source_version_id": version_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(source),
            "collect_audit_sha256": _sha_json(audits),
            "central_created_at": version.get("createdAt") or version.get("created_at"),
            "central_actor_id": self._actor_email(actor_id) or actor_id,
            "change_reason": reason,
            "reason_link_status": _reason_status(
                audits, version_id, version, logical_id,
                collect_reason=bool(collect_reason), change_summary=bool(change_summary),
                comment_reason=bool(comment_reason and not (collect_reason or central_reason)),
            ),
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": version_id,
        }
        form_version = getattr(self.client.config, "audit_form_version", "1")
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(
            audit_id, metadata, form_version, self.client.config.audit_form_id), {})
        return metadata

    def _prepare_comment_stack(self, plan: AuditPlan) -> None:
        """Pair newest Central comments with newest edits per submission."""
        groups: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
        for kind, form_id, logical_id, version_id, version in plan.tasks:
            if kind == "submission_version" and version_id != logical_id:
                groups.setdefault((form_id, logical_id), []).append((version_id, version))
        for (form_id, logical_id), versions in groups.items():
            comments = self.client.comments(form_id, logical_id)
            bodies: list[str] = []
            for comment in comments:
                body = str(comment.get("body") or "").strip()
                if body and body not in bodies:
                    bodies.append(body)
            if not bodies:
                continue
            minimum = datetime.min.replace(tzinfo=timezone.utc)
            versions.sort(key=lambda item: _event_time(item[1]) or minimum, reverse=True)
            for index, (version_id, _version) in enumerate(versions):
                # One comment may cover several subsequent edits.
                self._comment_reasons[(form_id, logical_id, version_id)] = bodies[min(index, len(bodies) - 1)]

    def _actor_email(self, actor_id: Any) -> str:
        resolver = getattr(self.client, "actor_email", None)
        if resolver is None:
            return ""
        return str(resolver(actor_id) or "")

    def _submit_checkpoint(self, *, forms_seen: int, versions_seen: int, run_id: str) -> None:
        audit_id = checkpoint_instance_id(self.project_id)
        metadata = {
            "record_type": "project_checkpoint",
            "project_id": self.project_id,
            "source_form_id": "",
            "source_instance_id": "",
            "source_version_id": "",
            "source_audit_instance_id": audit_id,
            "source_content_sha256": "",
            "collect_audit_sha256": "",
            "central_created_at": "",
            "central_actor_id": "",
            "change_reason": f"forms_seen={forms_seen};versions_seen={versions_seen}",
            "reason_link_status": "sentinel_checkpoint",
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": str(versions_seen),
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(
            audit_id, metadata, getattr(self.client.config, "audit_form_version", "1"),
            self.client.config.audit_form_id), {})

    def _previous_manifest_reference(self) -> dict[str, str]:
        """Find and verify the latest retained run manifest in Central."""
        candidates: list[tuple[datetime, dict[str, str]]] = []
        try:
            submissions = self.client.submissions(self.client.config.audit_form_id)
        except CentralError:
            return {"status": "previous_manifest_unavailable"}
        for submission in submissions:
            instance_id = str(submission.get("instanceId") or submission.get("id") or "")
            if not instance_id:
                continue
            try:
                xml = self.client.version_xml(self.client.config.audit_form_id, instance_id, instance_id)
                root = ET.fromstring(xml)
            except (CentralError, ET.ParseError):
                continue
            values = {
                element.tag.rsplit("}", 1)[-1]: str(element.text or "")
                for element in root
            }
            if values.get("record_type") not in {"run_timestamp_manifest", "sentinel_run_qa_snapshot"}:
                continue
            manifest_hash = values.get("timestamp_batch_sha256", "")
            if not manifest_hash:
                continue
            timestamp = _parse_time(submission.get("createdAt") or values.get("central_created_at"))
            if timestamp is None:
                timestamp = datetime.min.replace(tzinfo=timezone.utc)
            status = "previous_manifest_verified"
            try:
                attachments = self.client.version_attachments(
                    self.client.config.audit_form_id, instance_id, instance_id
                )
            except CentralError:
                attachments = []
                status = "previous_manifest_attachment_unavailable"
            manifest_name = next((str(item.get("name")) for item in attachments
                                  if item.get("exists") and str(item.get("name", "")).endswith("timestamp_manifest.json")), None)
            if manifest_name and status == "previous_manifest_verified":
                try:
                    attached_hash = _sha(self.client.attachment_bytes(
                        self.client.config.audit_form_id, instance_id, instance_id, manifest_name
                    ))
                    if attached_hash != manifest_hash:
                        status = "previous_manifest_hash_mismatch"
                except CentralError:
                    status = "previous_manifest_attachment_unavailable"
            else:
                status = "previous_manifest_attachment_missing"
            candidates.append((timestamp, {
                "status": status,
                "audit_instance_id": instance_id,
                "manifest_sha256": manifest_hash,
            }))
        if not candidates:
            return {"status": "genesis"}
        return max(candidates, key=lambda item: item[0])[1]

    def _submit_run_manifest(self, run_id: str, records: list[dict[str, Any]],
                             previous: dict[str, str], *, submit: bool = True):
        manifest = {
            "schema": "methodmesh.sentinel.sentinel_run_qa_snapshot.v1",
            "project_id": self.project_id,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "chain": previous,
            "record_types": {
                "source_form_version": "A deployed source-form definition version",
                "original_submission": "The original Central submission version",
                "submission_edit": "A later Central-retained edit of a submission",
                "project_checkpoint": "The project crawl checkpoint",
                "sentinel_run_qa_snapshot": "The consolidated QA/evidence snapshot for this Sentinel run",
                "validation_certificate": "Automated checks for this Sentinel run",
                "project_health_snapshot": "Project-level Central API health and inventory observation",
                "project_user_roles_snapshot": "Project-visible Web User and role-assignment observation",
            },
            "records": records,
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        manifest_hash = _sha(manifest_bytes)
        evidence = self._timestamp_manifest(manifest_bytes)
        audit_id = run_manifest_instance_id(self.project_id, run_id)
        fields = {
            "record_type": "sentinel_run_qa_snapshot",
            "project_id": self.project_id,
            "source_form_id": "",
            "source_instance_id": "",
            "source_version_id": "",
            "source_audit_instance_id": audit_id,
            "source_content_sha256": "",
            "collect_audit_sha256": "",
            "central_created_at": manifest["created_at"],
            "central_actor_id": "",
            "change_reason": f"Sentinel run manifest; chain={previous.get('status', 'unknown')}"[:64],
            "reason_link_status": "sentinel_run_manifest",
            "timestamp_status": evidence.status,
            "timestamp_time": evidence.time,
            "timestamp_batch_id": run_id,
            "timestamp_batch_sha256": manifest_hash,
            "timestamp_manifest": "timestamp_manifest.json",
            "timestamp_token": "timestamp_token.tsr" if evidence.token else "",
            "timestamp_token_sha256": _sha(evidence.token) if evidence.token else "",
            "timestamp_certificate": "timestamp_certificate.pem" if evidence.certificate else "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": str(len(records)),
        }
        attachments = self._timestamp_attachments(manifest_bytes, evidence)
        if submit:
            self.sink.submit(
                self.client.config.audit_form_id,
                _audit_xml(audit_id, fields, getattr(self.client.config, "audit_form_version", "1"),
                           self.client.config.audit_form_id),
                attachments,
            )
        return fields, attachments

    def _submit_validation_certificate(self, run_id: str, plan: AuditPlan,
                                       records: list[dict[str, Any]],
                                       previous: dict[str, str],
                                       manifest_fields: dict[str, str], *, submit: bool = True):
        ids = [record.get("audit_instance_id", "") for record in records]
        checks = [
            _validation_check("audit_form_configured", bool(self.client.config.audit_form_id), "Audit form configured"),
            _validation_check("source_scope_discovered", bool(plan.forms), "Configured source-form scope discovered"),
            _validation_check("deterministic_ids_unique", len(ids) == len(set(ids)), "No duplicate audit IDs in run"),
            _validation_check(
                "run_reconciled", len(records) == len(plan.tasks),
                "Every planned source task has a run result; run evidence is consolidated below",
            ),
            _validation_check(
                "manifest_chain", previous.get("status") in {"genesis", "previous_manifest_verified"},
                f"Previous manifest status: {previous.get('status', 'unknown')}",
                warning=True,
            ),
            _validation_check(
                "run_manifest_timestamp", manifest_fields.get("timestamp_status") == "rfc3161_verified",
                f"Run manifest timestamp: {manifest_fields.get('timestamp_status', 'unknown')}",
                warning=True,
            ),
        ]
        failures = [check for check in checks if check["status"] == "fail"]
        warnings = [check for check in checks if check["status"] == "warning"]
        status = "failed" if failures else ("passed_with_warnings" if warnings else "passed")
        certificate = {
            "schema": "methodmesh.sentinel.validation_certificate.v1",
            "project_id": self.project_id,
            "validation_run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status,
            "checks": checks,
            "summary": {
                "forms": len(plan.forms),
                "planned_records": len(plan.tasks),
                "run_records": len(records),
                "platform_snapshots": 1,
                "user_role_snapshots": 1,
                "submitted": sum(record.get("status") == "submitted" for record in records),
                "already_present": sum(record.get("status") == "already_present" for record in records),
            },
            "run_manifest": {
                "audit_instance_id": manifest_fields.get("source_audit_instance_id", ""),
                "sha256": manifest_fields.get("timestamp_batch_sha256", ""),
                "timestamp_status": manifest_fields.get("timestamp_status", ""),
            },
        }
        certificate_bytes = (json.dumps(certificate, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        certificate_pdf = _json_document_pdf(certificate, "Sentinel validation certificate")
        audit_id = run_manifest_instance_id(self.project_id, run_id)
        fields = {
            "record_type": "sentinel_run_qa_snapshot",
            "project_id": self.project_id,
            "source_form_id": "",
            "source_instance_id": "",
            "source_version_id": run_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(certificate_bytes),
            "collect_audit_sha256": "",
            "central_created_at": certificate["created_at"],
            "central_actor_id": "",
            "change_reason": f"Validation certificate; status={status}"[:64],
            "reason_link_status": "sentinel_validation",
            "timestamp_status": "covered_by_run_manifest",
            "timestamp_time": "",
            "timestamp_batch_id": run_id,
            "timestamp_batch_sha256": manifest_fields.get("timestamp_batch_sha256", ""),
            "timestamp_manifest": "",
            "timestamp_token": "",
            "timestamp_token_sha256": "",
            "timestamp_certificate": "",
            "platform_snapshot": "",
            "platform_snapshot_pdf": "",
            "validation_report": "validation_report.json",
            "validation_certificate": "validation_certificate.pdf" if certificate_pdf else "",
            "evidence_package": "",
            "sentinel_run_id": run_id,
            "checkpoint_cursor": str(len(records)),
        }
        certificate_attachments = {"validation_report.json": certificate_bytes}
        if certificate_pdf:
            certificate_attachments["validation_certificate.pdf"] = certificate_pdf
        if submit:
            self.sink.submit(
                self.client.config.audit_form_id,
                _audit_xml(run_manifest_instance_id(self.project_id, run_id), fields,
                           getattr(self.client.config, "audit_form_version", "1"),
                           self.client.config.audit_form_id),
                certificate_attachments,
            )
        return fields, certificate_attachments

    def _timestamp_manifest(self, manifest: bytes) -> TimestampEvidence:
        policy = getattr(self.client.config, "timestamp_policy", "preferred").lower()
        if policy == "disabled":
            return TimestampEvidence(status="timestamping_disabled")
        try:
            return timestamp_manifest(manifest, self.client.config.timestamp_url)
        except TimestampError as error:
            if policy == "required":
                raise CentralError(f"Required RFC3161 timestamp failed: {error}") from error
            if getattr(self.client, "debug", False):
                print(f"[debug] RFC3161 timestamp unavailable; preserving manifest only: {error}", file=sys.stderr)
            return TimestampEvidence(status="manifest_created_not_timestamped", detail=str(error))

    @staticmethod
    def _timestamp_attachments(manifest: bytes, evidence: TimestampEvidence) -> dict[str, bytes]:
        attachments = {"timestamp_manifest.json": manifest}
        if evidence.token:
            attachments["timestamp_token.tsr"] = evidence.token
        if evidence.certificate:
            attachments["timestamp_certificate.pem"] = evidence.certificate
        return attachments


def _audit_xml(instance_id: str, fields: dict[str, str], form_version: str,
               form_id: str = "sentinel_project_audit") -> bytes:
    values = "".join(f"<{key}>{escape(_xml_safe(value))}</{key}>" for key, value in fields.items())
    return (f'<?xml version="1.0" encoding="UTF-8"?><data id="{escape(form_id)}" version="{escape(form_version)}" '
            'xmlns:orx="http://openrosa.org/xforms">'
            f"{values}<orx:meta><orx:instanceID>{escape(_xml_safe(instance_id))}</orx:instanceID></orx:meta></data>").encode()


def snapshot_attachment_fields(form_version: str, json_field: str, pdf_field: str,
                                json_filename: str, pdf_filename: str) -> dict[str, str]:
    """Use dedicated evidence fields in audit form v5+, retaining v4 fallback."""
    try:
        dedicated = int(str(form_version).lstrip("vV")) >= 5
    except ValueError:
        dedicated = False
    fields = {"platform_snapshot": "", "platform_snapshot_pdf": ""}
    if dedicated:
        fields[json_field] = json_filename
        fields[pdf_field] = pdf_filename
    else:
        fields["platform_snapshot"] = "platform_snapshot.json"
        fields["platform_snapshot_pdf"] = "platform_snapshot.pdf" if pdf_filename else ""
    return fields


def snapshot_attachment_names(fields: dict[str, str], json_field: str, pdf_field: str) -> tuple[str, str]:
    """Return the attachment filenames named by a v4-compatible field map."""
    return (fields.get(json_field) or fields["platform_snapshot"],
            fields.get(pdf_field) or fields["platform_snapshot_pdf"])


def _xml_safe(value: Any) -> str:
    text = str(value or "")
    return "".join(
        character for character in text
        if ord(character) in (0x9, 0xA, 0xD)
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )


def _json_document_pdf(document: dict[str, Any], title: str) -> bytes:
    """Render a compact human-readable PDF companion for a JSON evidence file."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ModuleNotFoundError:
        return b""
    from io import BytesIO

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontName = "Helvetica"
    body.fontSize = 8
    body.leading = 10
    story: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 6 * mm)]

    def add_value(key: str, value: Any, level: int = 0) -> None:
        indent = "&nbsp;" * (level * 5)
        if isinstance(value, dict):
            story.append(Paragraph(f"{indent}<b>{escape(str(key))}</b>", body))
            for child_key, child_value in value.items():
                add_value(str(child_key), child_value, level + 1)
        elif isinstance(value, list):
            story.append(Paragraph(f"{indent}<b>{escape(str(key))}</b>", body))
            for index, child_value in enumerate(value, 1):
                add_value(f"[{index}]", child_value, level + 1)
        else:
            rendered = "" if value is None else str(value)
            story.append(Paragraph(f"{indent}<b>{escape(str(key))}</b>: {escape(rendered)}", body))
        story.append(Spacer(1, 1.1 * mm))

    for key, value in document.items():
        add_value(str(key), value)
    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm).build(story)
    return buffer.getvalue()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def _central_action_is_relevant(action: str) -> bool:
    return action.startswith(("project.", "form.", "submission.")) or action in {
        "user.create", "user.update", "user.delete", "user.session.create",
        "field_key.session.end", "public_link.session.end",
    }


def _central_event_in_project(event: dict[str, Any], project_id: str, form_ids: set[str],
                              form_numeric_ids: set[str], submission_ids: set[str],
                              actor_ids: set[str]) -> bool:
    action = str(event.get("action") or "")
    actee = str(event.get("acteeId") or "")
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    values = {str(value) for value in _flatten_values(details)}
    if action.startswith("project."):
        return actee == str(project_id) or str(project_id) in values
    if actee in form_ids or actee in form_numeric_ids or actee in submission_ids:
        return True
    if form_ids.intersection(values) or form_numeric_ids.intersection(values):
        return True
    if str(project_id) in values:
        return True
    if action.startswith("user.") or action in {"field_key.session.end", "public_link.session.end"}:
        return actee in actor_ids or str(event.get("actorId") or "") in actor_ids or bool(actor_ids.intersection(values))
    return False


def _flatten_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        result: list[Any] = []
        for child in value.values():
            result.extend(_flatten_values(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_flatten_values(child))
        return result
    return [value]


def _central_event_key(event: dict[str, Any]) -> str:
    return str(event.get("id") or _sha(json.dumps(event, sort_keys=True, ensure_ascii=False).encode())[:48])


def _central_record_type(action: str) -> str:
    words = action.replace(".", "_")
    return f"central_{words}"


def _central_event_summary(action: str, details: dict[str, Any]) -> str:
    for key in ("note", "notes", "actionNotes", "reason"):
        if details.get(key):
            return f"{action}: {str(details[key])[:48]}"[:64]
    return action[:64]


def _validation_check(name: str, passed: bool, detail: str, *, warning: bool = False) -> dict[str, str]:
    if passed:
        status = "pass"
    elif warning:
        status = "warning"
    else:
        status = "fail"
    return {"name": name, "status": status, "detail": detail}


def _run_id() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"sentinel-run-{now}"


def run_manifest_instance_id(project_id: str, run_id: str) -> str:
    material = f"run-manifest\x1f{project_id}\x1f{run_id}".encode()
    return "uuid:sentinel-manifest-" + hashlib.sha256(material).hexdigest()[:39]


def _reason(audits: list[dict[str, Any]], version_id: str, version: dict[str, Any], logical_id: str) -> str:
    """Extract an edit note from the Central audit event for this version.

    Central comments are submission-level and do not identify a version.  The
    server audit event is the record that can be linked to an edit, commonly
    through details.versionId and/or an action note.
    """
    values: list[str] = []
    events = [event for event in audits if _audit_event_matches(event, version_id, version, logical_id)]
    if version_id != logical_id and not any(version_id in _referenced_values(event) for event in events):
        events = _nearest_edit_events(audits, version)
    for event in events:
        for value in _note_values(event):
            if value and value not in values:
                values.append(value)
    return " | ".join(values)


def _nearest_edit_events(audits: list[dict[str, Any]], version: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair a version with the nearby server-side edit/comment events.

    Central's comments endpoint has no timestamp or version ID.  The server
    audit stream does have ``loggedAt`` and is ordered newest first, so when an
    edit event lacks an explicit version reference we use the version's
    ``createdAt`` as the anchor and include the nearest edit plus the nearest
    preceding comment by the same actor.
    """
    version_time = _event_time(version)
    if version_time is None:
        return []
    updates = [
        event for event in audits
        if "submission.update" in str(event.get("action", "")).lower()
        and _event_time(event) is not None
    ]
    if not updates:
        return []
    update = min(updates, key=lambda event: abs((_event_time(event) - version_time).total_seconds()))
    update_time = _event_time(update)
    if update_time is None or abs((update_time - version_time).total_seconds()) > 300:
        return []
    result = [update]
    actor = update.get("actorId")
    comments = [
        event for event in audits
        if "comment" in str(event.get("action", "")).lower()
        and _event_time(event) is not None
        and _event_time(event) <= update_time
        and (actor is None or event.get("actorId") in (None, actor))
    ]
    if comments:
        result.insert(0, max(comments, key=lambda event: _event_time(event)))
    return result


def _event_time(value: dict[str, Any]) -> datetime | None:
    raw = value.get("loggedAt") or value.get("createdAt") or value.get("created_at")
    return _parse_time(raw)


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _reason_status(audits: list[dict[str, Any]], version_id: str, version: dict[str, Any], logical_id: str,
                   *, collect_reason: bool = False, change_summary: bool = False,
                   comment_reason: bool = False) -> str:
    if version_id == logical_id:
        return "not_applicable"
    if collect_reason:
        return "linked_collect_audit"
    if _reason(audits, version_id, version, logical_id):
        return "linked_central_audit"
    if comment_reason:
        return "unlinked_central_comment"
    if change_summary:
        return "edit_recorded_reason_missing"
    if any(_audit_event_matches(event, version_id, version, logical_id) for event in audits):
        return "edit_reason_not_recorded"
    return "no_linked_edit_audit"


def _audit_event_matches(event: dict[str, Any], version_id: str, version: dict[str, Any], logical_id: str) -> bool:
    if version_id == logical_id:
        return str(event.get("action", "")).lower() in {"submission.create", "submission.create.version"}
    references = _referenced_values(event)
    if version_id in references:
        return True
    action = str(event.get("action", "")).lower()
    return "submission.update" in action or action in {"submission.edit", "submission.version.create"}


def _referenced_values(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = _normalise_key(key)
            if key_lower in {"versionid", "submissionversionid", "newversionid", "instanceid", "newinstanceid"}:
                if child is not None:
                    found.add(str(child))
            found.update(_referenced_values(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_referenced_values(child))
    return found


def _note_values(event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    keys = {"reason", "note", "notes", "actionnotes", "changereason", "comment", "body", "message"}

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, _normalise_key(child_key))
        elif key in keys and value not in (None, ""):
            text = str(value)
            if text not in values:
                values.append(text)

    visit(event)
    return values


def is_edit_candidate(version_id: str, logical_id: str) -> bool:
    return version_id != logical_id


def _collect_audit_bytes(client: Any, form_id: str, logical_id: str, version_id: str) -> bytes:
    listing = getattr(client, "version_attachments", None)
    downloader = getattr(client, "attachment_bytes", None)
    if listing is None or downloader is None:
        return b""
    for item in listing(form_id, logical_id, version_id):
        name = str(item.get("name") or "")
        if item.get("exists") and name.lower().endswith("audit.csv"):
            return downloader(form_id, logical_id, version_id, name)
    return b""


def _collect_reason(data: bytes) -> str:
    if not data:
        return ""
    try:
        rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig", "replace")))
    except csv.Error:
        return ""
    reasons: list[str] = []
    for row in rows:
        normalised = {_normalise_key(key): value for key, value in row.items() if key}
        event = _normalise_key(normalised.get("event", ""))
        if "changereason" not in event and "changereason" not in normalised:
            continue
        value = normalised.get("changereason") or normalised.get("reason") or ""
        if value and value not in reasons:
            reasons.append(value)
    return " | ".join(reasons)


def _change_summary(diffs: Any, version_id: str) -> str:
    changes = diffs.get(version_id) if isinstance(diffs, dict) else None
    if not isinstance(changes, list):
        return ""
    values: list[str] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        path = "/" + "/".join(str(part) for part in change.get("path", []))
        if path in {"/meta/instanceID", "/meta/instanceName", "/meta/deprecatedID"}:
            continue
        old = "(blank)" if change.get("old") in (None, "") else str(change.get("old"))
        new = "(blank)" if change.get("new") in (None, "") else str(change.get("new"))
        values.append(f"{path}: {old} -> {new}")
    return "; ".join(values)


def _combine_reason(change_summary: str, reason: str) -> str:
    parts = []
    if change_summary:
        parts.append(f"Changed: {change_summary}")
    if reason:
        parts.append(f"Reason: {reason}")
    return " | ".join(parts)


def _normalise_key(value: Any) -> str:
    return str(value or "").lower().replace("_", "").replace("-", "").replace(" ", "")


def _is_existing_record(error: CentralError) -> bool:
    message = str(error)
    return "409.3" in message and "already exists" in message
