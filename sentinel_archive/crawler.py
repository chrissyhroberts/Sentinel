from __future__ import annotations

import hashlib
import io
import json
import zipfile
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


class ProjectAuditor:
    """Audit every source form in one configured Central project."""

    def __init__(self, client: CentralClient, sink: AuditSink | None = None):
        self.client = client
        self.sink = sink or client
        self.project_id = client.config.project_id

    def run(self) -> RunSummary:
        completed = self._existing_audit_ids()
        forms = [form for form in self.client.forms() if form.get("xmlFormId") != self.client.config.audit_form_id]
        seen = submitted = skipped = form_versions_submitted = 0
        for form in forms:
            form_id = str(form.get("xmlFormId") or form.get("formId"))
            if not form_id:
                continue
            seen += 1
            for form_version in self.client.form_versions(form_id):
                form_version_id = str(form_version.get("version") or form_version.get("id") or "")
                if not form_version_id:
                    continue
                record_id = audit_instance_id(self.project_id, form_id, "form-definition", form_version_id)
                if record_id in completed:
                    skipped += 1
                    continue
                self._submit_form_version(form_id, form_version_id, form_version)
                form_versions_submitted += 1
            for submission in self.client.submissions(form_id):
                logical_id = str(submission.get("instanceId") or submission.get("id"))
                if not logical_id:
                    continue
                for version in self.client.versions(form_id, logical_id):
                    version_id = str(version.get("instanceId") or version.get("versionId") or version.get("id"))
                    if not version_id:
                        continue
                    record_id = audit_instance_id(self.project_id, form_id, logical_id, version_id)
                    if record_id in completed:
                        skipped += 1
                        continue
                    self._submit_version(form_id, logical_id, version_id, version)
                    submitted += 1
        checkpoint_id = checkpoint_instance_id(self.project_id)
        if checkpoint_id not in completed:
            self._submit_checkpoint(forms_seen=seen, versions_seen=submitted + skipped)
        return RunSummary(self.project_id, seen, submitted + skipped, submitted, skipped, form_versions_submitted)

    def _submit_form_version(self, form_id: str, version_id: str, metadata: dict[str, Any]) -> None:
        xml = self.client.form_version_bytes(form_id, version_id, "xml")
        files = {"form.xml": xml}
        try:
            files["form.xlsx"] = self.client.form_version_bytes(form_id, version_id, "xlsx")
        except Exception:
            pass
        bundle = _bundle(xml, files, [], [], {"form_version": metadata})
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
            "sentinel_run_id": "",
            "checkpoint_cursor": version_id,
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, fields, "source_bundle.zip"),
                         {"source_bundle.zip": bundle})

    def _existing_audit_ids(self) -> set[str]:
        result: set[str] = set()
        for submission in self.client.submissions(self.client.config.audit_form_id):
            value = submission.get("instanceId") or submission.get("id")
            if value:
                result.add(str(value))
        return result

    def _submit_version(self, form_id: str, logical_id: str, version_id: str, version: dict[str, Any]) -> None:
        source = self.client.version_xml(form_id, logical_id, version_id)
        metadata = self.client.version_metadata(form_id, logical_id, version_id)
        attachments: dict[str, bytes] = {}
        for item in metadata.get("attachments", []) or []:
            if not item.get("exists", True):
                continue
            filename = str(item.get("filename") or item.get("name") or "")
            if filename:
                attachments[filename] = self.client.attachment_bytes(form_id, logical_id, version_id, filename)
        audits = self.client.audits(form_id, logical_id)
        comments = self.client.comments(form_id, logical_id)
        try:
            diffs = self.client.diffs(form_id, logical_id)
        except Exception as error:  # Central installations may not expose diffs.
            diffs = {"status": "unavailable", "error_class": type(error).__name__}
        bundle = _bundle(source, attachments, audits, comments, diffs)
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
            "sentinel_run_id": "",
            "checkpoint_cursor": version_id,
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, metadata, "source_bundle.zip"),
                         {"source_bundle.zip": bundle})

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
            "sentinel_run_id": "",
            "checkpoint_cursor": str(versions_seen),
        }
        self.sink.submit(self.client.config.audit_form_id, _audit_xml(audit_id, metadata, ""), {})


def _bundle(source: bytes, attachments: dict[str, bytes], audits: list[dict[str, Any]],
            comments: list[dict[str, Any]], diffs: Any) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("submission.xml", source)
        for filename, content in attachments.items():
            archive.writestr("attachments/" + filename.replace("..", "_"), content)
        archive.writestr("central/audits.json", json.dumps(audits, indent=2, ensure_ascii=False))
        archive.writestr("central/comments.json", json.dumps(comments, indent=2, ensure_ascii=False))
        archive.writestr("central/diffs.json", json.dumps(diffs, indent=2, ensure_ascii=False))
    return output.getvalue()


def _audit_xml(instance_id: str, fields: dict[str, str], bundle_name: str) -> bytes:
    values = "".join(f"<{key}>{escape(str(value or ''))}</{key}>" for key, value in fields.items())
    values += f"<source_bundle>{escape(bundle_name)}</source_bundle>"
    return (f'<?xml version="1.0" encoding="UTF-8"?><data id="sentinel_project_audit">'
            f"{values}<meta><instanceID>{escape(instance_id)}</instanceID></meta></data>").encode()


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
