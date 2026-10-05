from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any, Protocol
from xml.sax.saxutils import escape

from .central import CentralClient
from .project import audit_instance_id, checkpoint_instance_id


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

    def plan(self) -> AuditPlan:
        all_forms = self.client.forms()
        audit_form = self.client.config.audit_form_id
        if not any((form.get("xmlFormId") or form.get("formId")) == audit_form for form in all_forms):
            raise RuntimeError(f"Audit form {audit_form!r} was not found in project {self.project_id}")
        forms = tuple(form for form in all_forms if (form.get("xmlFormId") or form.get("formId")) != audit_form)
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
        return AuditPlan(forms, tuple(tasks), frozenset(self._existing_audit_ids()))

    def run(self, plan: AuditPlan | None = None) -> RunSummary:
        plan = plan or self.plan()
        completed = set(plan.existing_audit_ids)
        forms = plan.forms
        seen = submitted = skipped = form_versions_submitted = 0
        seen = len(forms)
        for kind, form_id, logical_id, version_id, metadata in plan.tasks:
            record_id = audit_instance_id(self.project_id, form_id, logical_id, version_id)
            if record_id in completed:
                skipped += 1
                continue
            if getattr(self.client, "debug", False):
                label = f"{form_id}/{version_id}" if kind == "form_version" else f"{form_id}/{logical_id}/{version_id}"
                print(f"[debug] archiving {kind}: {label}", file=sys.stderr)
            if kind == "form_version":
                self._submit_form_version(form_id, version_id, metadata)
                form_versions_submitted += 1
            else:
                self._submit_version(form_id, logical_id, version_id, metadata)
                submitted += 1
        checkpoint_id = checkpoint_instance_id(self.project_id)
        if checkpoint_id not in completed:
            self._submit_checkpoint(forms_seen=seen, versions_seen=submitted + skipped)
        return RunSummary(self.project_id, seen, submitted + skipped, submitted, skipped, form_versions_submitted)

    def _submit_form_version(self, form_id: str, version_id: str, metadata: dict[str, Any]) -> None:
        xml = self.client.form_version_bytes(form_id, version_id, "xml")
        audit_id = audit_instance_id(self.project_id, form_id, "form-definition", version_id)
        fields = {
            "record_type": "form_version",
            "project_id": self.project_id,
            "source_form_id": form_id,
            "source_instance_id": "form-definition",
            "source_version_id": version_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(xml),
            "collect_audit_sha256": "",
            "central_created_at": metadata.get("createdAt") or metadata.get("created_at"),
            "central_actor_id": metadata.get("actorId") or "",
            "change_reason": "",
            "reason_link_status": "not_applicable",
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_token": "",
            "sentinel_run_id": "",
            "checkpoint_cursor": version_id,
        }
        form_version = getattr(self.client.config, "audit_form_version", "1")
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, fields, form_version), {})

    def _existing_audit_ids(self) -> set[str]:
        result: set[str] = set()
        for submission in self.client.submissions(self.client.config.audit_form_id):
            value = submission.get("instanceId") or submission.get("id")
            if value:
                result.add(str(value))
        return result

    def _submit_version(self, form_id: str, logical_id: str, version_id: str, version: dict[str, Any]) -> None:
        source = self.client.version_xml(form_id, logical_id, version_id)
        audits = self.client.audits(form_id, logical_id)
        comments = self.client.comments(form_id, logical_id)
        audit_id = audit_instance_id(self.project_id, form_id, logical_id, version_id)
        metadata = {
            "record_type": "submission_version",
            "project_id": self.project_id,
            "source_form_id": form_id,
            "source_instance_id": logical_id,
            "source_version_id": version_id,
            "source_audit_instance_id": audit_id,
            "source_content_sha256": _sha(source),
            "collect_audit_sha256": _sha_json(audits),
            "central_created_at": version.get("createdAt") or version.get("created_at"),
            "central_actor_id": version.get("actorId") or version.get("submitterId"),
            "change_reason": _reason(comments, version_id),
            "reason_link_status": _reason_status(comments, version_id),
            "timestamp_status": "not_requested",
            "timestamp_time": "",
            "timestamp_batch_id": "",
            "timestamp_batch_sha256": "",
            "timestamp_token": "",
            "sentinel_run_id": "",
            "checkpoint_cursor": version_id,
        }
        form_version = getattr(self.client.config, "audit_form_version", "1")
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, metadata, form_version), {})

    def _submit_checkpoint(self, *, forms_seen: int, versions_seen: int) -> None:
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
            "timestamp_token": "",
            "sentinel_run_id": "",
            "checkpoint_cursor": str(versions_seen),
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, metadata, ""), {})


def _audit_xml(instance_id: str, fields: dict[str, str], form_version: str) -> bytes:
    values = "".join(f"<{key}>{escape(_xml_safe(value))}</{key}>" for key, value in fields.items())
    return (f'<?xml version="1.0" encoding="UTF-8"?><data id="sentinel_project_audit" version="{escape(form_version)}" '
            'xmlns:orx="http://openrosa.org/xforms">'
            f"{values}<orx:meta><orx:instanceID>{escape(_xml_safe(instance_id))}</orx:instanceID></orx:meta></data>").encode()


def _xml_safe(value: Any) -> str:
    text = str(value or "")
    return "".join(
        character for character in text
        if ord(character) in (0x9, 0xA, 0xD)
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def _reason(comments: list[dict[str, Any]], version_id: str) -> str:
    linked = [c.get("body", "") for c in comments if c.get("versionId") == version_id or c.get("version_id") == version_id]
    return " | ".join(str(value) for value in linked if value)


def _reason_status(comments: list[dict[str, Any]], version_id: str) -> str:
    if any(c.get("versionId") == version_id or c.get("version_id") == version_id for c in comments):
        return "linked_central_comment"
    return "no_linked_reason_recorded"
