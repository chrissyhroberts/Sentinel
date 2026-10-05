from __future__ import annotations

import hashlib
import html
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "sentinel.archival_record.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class VersionInput:
    form_id: str
    instance_id: str
    version_id: str
    submission: Path
    audit_trail: Path | None = None
    attachments: tuple[Path, ...] = ()
    central_metadata: dict[str, Any] = field(default_factory=dict)
    change_events: tuple[dict[str, Any], ...] = ()
    timestamp: dict[str, Any] | None = None


class ArchiveStore:
    """Archive exact Central bytes and produce a readable version ledger.

    This deliberately does not parse, normalise, reconstruct, or canonicalise
    submission content. Each retained Central version is independently
    evidenced by the bytes Sentinel received.
    """

    def __init__(self, root: Path):
        self.root = root

    def archive_version(self, item: VersionInput) -> dict[str, Any]:
        destination = (
            self.root
            / "forms"
            / _safe(item.form_id)
            / "instances"
            / _safe(item.instance_id)
            / "versions"
            / _safe(item.version_id)
        )
        destination.mkdir(parents=True, exist_ok=True)

        submission_path = destination / item.submission.name
        _copy_exact(item.submission, submission_path)
        files = [{"role": "submission", "path": submission_path.name,
                  "sha256": sha256_file(submission_path)}]

        if item.audit_trail:
            audit_path = destination / item.audit_trail.name
            _copy_exact(item.audit_trail, audit_path)
            files.append({"role": "collect_audit_trail", "path": audit_path.name,
                          "sha256": sha256_file(audit_path)})

        attachment_dir = destination / "attachments"
        for attachment in item.attachments:
            attachment_dir.mkdir(exist_ok=True)
            target = attachment_dir / attachment.name
            _copy_exact(attachment, target)
            files.append({"role": "attachment",
                          "path": str(target.relative_to(destination)),
                          "sha256": sha256_file(target)})

        record = {
            "schema": SCHEMA,
            "archived_at": utc_now(),
            "form_id": item.form_id,
            "instance_id": item.instance_id,
            "version_id": item.version_id,
            "central": item.central_metadata,
            "files": files,
            "timestamp": item.timestamp or {"status": "not_requested"},
            "change_events": list(item.change_events),
            "canonical_reconstruction": "not_performed",
            "previous_attestation_hash": None,
        }
        _write_json(destination / "version_manifest.json", record)
        self._update_instance_index(item, record)
        return record

    def _update_instance_index(self, item: VersionInput, record: dict[str, Any]) -> None:
        instance_dir = self.root / "forms" / _safe(item.form_id) / "instances" / _safe(item.instance_id)
        index_path = instance_dir / "audit_record.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            index = {
                "schema": "sentinel.archival_audit_record.v1",
                "form_id": item.form_id,
                "instance_id": item.instance_id,
                "versions": [],
            }
        index["versions"] = [v for v in index["versions"] if v["version_id"] != item.version_id]
        index["versions"].append({
            "version_id": item.version_id,
            "central_created_at": item.central_metadata.get("createdAt"),
            "central_actor": item.central_metadata.get("actor"),
            "timestamp_status": (item.timestamp or {}).get("status", "not_requested"),
            "manifest": f"versions/{_safe(item.version_id)}/version_manifest.json",
        })
        index["versions"].sort(key=lambda value: (value.get("central_created_at") or "", value["version_id"]))
        _write_json(index_path, index)
        self._write_html(instance_dir / "audit_record.html", index, index_path.parent)

    def _write_html(self, path: Path, index: dict[str, Any], instance_dir: Path) -> None:
        rows: list[str] = []
        for version in index["versions"]:
            manifest = json.loads((instance_dir / version["manifest"]).read_text(encoding="utf-8"))
            reasons = []
            for event in manifest.get("change_events", []):
                reason = event.get("reason") or event.get("comment") or event.get("body")
                if reason:
                    reasons.append(str(reason))
            reason_html = "<br>".join(html.escape(value) for value in reasons) or "<em>none recorded</em>"
            files = "<br>".join(html.escape(f"{f['role']}: {f['sha256']}") for f in manifest["files"])
            rows.append(
                "<tr>"
                f"<td>{html.escape(version['version_id'])}</td>"
                f"<td>{html.escape(version.get('central_created_at') or 'unknown')}</td>"
                f"<td>{html.escape(version.get('central_actor') or 'unknown')}</td>"
                f"<td>{html.escape(version['timestamp_status'])}</td>"
                f"<td>{files}</td><td>{reason_html}</td>"
                "</tr>"
            )
        body = "\n".join(rows)
        content = f"""<!doctype html>
<meta charset="utf-8"><title>Sentinel audit record</title>
<h1>Sentinel audit record</h1>
<p><b>Form:</b> {html.escape(index['form_id'])}<br>
<b>Instance:</b> {html.escape(index['instance_id'])}</p>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr><th>Version</th><th>Central time</th><th>Actor</th><th>Timestamp</th><th>Archived bytes</th><th>Change reason</th></tr></thead>
<tbody>{body}</tbody></table>
<p>Exact bytes are preserved beside each version manifest. Canonical reconstruction was not performed.</p>
"""
        path.write_text(content, encoding="utf-8")


def _copy_exact(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    shutil.copyfile(source, target)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
    return clean or "_"
