"""Read-only, machine-readable validation checks for a configured project run."""

from __future__ import annotations

import json
import hashlib
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .central import CentralError
from .crawler import AuditPlan, _sha
from .project import audit_instance_id
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class ValidationCheck:
    check_id: str
    component: str
    mode: str
    status: str
    detail: str
    evidence_ref: str = ""


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
    report = {
        "schema": "methodmesh.sentinel.validation_report.v1",
        "project_id": str(config.project_id),
        "components": ["ODK Central", "ODK Collect", "Enketo", "MethodMesh", "Sentinel"],
        "mode": "read_only",
        "status": "failed" if failures else "passed",
        "summary": {"checks": len(checks), "passed": len(checks) - failures, "failed": failures},
        "checks": [asdict(check) for check in checks],
    }
    for check in report["checks"]:
        check["evidence_ref"] = "validation_report.json"
    return report


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


def run_active_validation(client: Any) -> dict[str, Any]:
    """Create and edit one synthetic Central validation record, then verify it."""
    form_id = next(
        (value for value in getattr(client.config, "validation_form_ids", ())
         if value == "sentinel_validation_central"),
        "sentinel_validation_central",
    )
    run_id = "active-" + uuid.uuid4().hex[:16]
    initial_id = "uuid:sentinel-validation-" + uuid.uuid4().hex
    edited_id = "uuid:sentinel-validation-" + uuid.uuid4().hex
    device_id = "sentinel-validation-harness"
    initial_xml = _validation_xml(form_id, initial_id, run_id, "CENTRAL-A", "initial", "")
    edited_xml = _validation_xml(
        form_id, edited_id, run_id, "CENTRAL-B", "edited",
        "Controlled Sentinel validation edit",
        deprecated_id=initial_id,
    )
    checks: list[dict[str, str]] = []

    def add(check_id: str, passed: bool, detail: str, evidence: str = "validation_report.json") -> None:
        checks.append({
            "check_id": check_id,
            "component": "ODK Central" if check_id.startswith("central_") else "Sentinel",
            "mode": "automated",
            "status": "pass" if passed else "fail",
            "detail": detail,
            "evidence_ref": evidence,
        })

    try:
        created = client.create_validation_submission(form_id, initial_xml, device_id=device_id)
        logical_id = str(created.get("instanceId") or initial_id)
        created_xml = client.submission_xml(form_id, logical_id)
        created_root = ET.fromstring(created_xml)
        created_value = _xml_field(created_root, "test_value")
        add("central_active_create", created_value == "CENTRAL-A",
            f"Created and retrieved synthetic submission {logical_id}")
        initial_hash = _sha(created_xml)

        client.update_validation_submission(
            form_id, logical_id, edited_xml,
            action_notes="Sentinel validation changed test_value from CENTRAL-A to CENTRAL-B",
        )
        versions = client.versions(form_id, logical_id)
        current_xml = client.submission_xml(form_id, logical_id)
        current_root = ET.fromstring(current_xml)
        current_value = _xml_field(current_root, "test_value")
        diffs = client.diffs(form_id, logical_id)
        audits = client.audits(form_id, logical_id)
        diff_text = json.dumps(diffs, sort_keys=True)
        audit_text = json.dumps(audits, sort_keys=True)
        add("central_active_edit", current_value == "CENTRAL-B" and len(versions) >= 2,
            f"Retrieved edited value and {len(versions)} retained submission versions")
        add("central_active_diff", "CENTRAL-A" in diff_text and "CENTRAL-B" in diff_text,
            "Central diff evidence contains the expected old and new values")
        add("central_active_reason", "Controlled Sentinel validation edit" in _xml_field(current_root, "change_reason")
            or "Controlled Sentinel validation" in audit_text,
            "The controlled edit reason is present in the submission or Central audit evidence")
        add("sentinel_active_hash_change", initial_hash != _sha(current_xml),
            "Sentinel can distinguish the original and edited XML byte hashes")
    except (CentralError, ET.ParseError) as error:
        add("central_active_create", False, f"Active validation failed: {type(error).__name__}: {error}")

    failures = sum(check["status"] == "fail" for check in checks)
    return {
        "schema": "methodmesh.sentinel.validation_report.v1",
        "project_id": str(client.config.project_id),
        "components": ["ODK Central", "Sentinel"],
        "mode": "active_synthetic_validation",
        "validation_run_id": run_id,
        "validation_form_id": form_id,
        "status": "failed" if failures else "passed",
        "summary": {"checks": len(checks), "passed": len(checks) - failures, "failed": failures},
        "checks": checks,
        "safety": "Synthetic validation data only; no participant or source-study form was modified.",
    }


def _validation_xml(form_id: str, instance_id: str, run_id: str, value: str,
                    case: str, reason: str, *, deprecated_id: str = "") -> bytes:
    deprecated = f"<deprecatedID>{escape(deprecated_id)}</deprecatedID>" if deprecated_id else ""
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<data id="{escape(form_id)}" version="1" xmlns:orx="http://openrosa.org/xforms">'
        f'<orx:meta><orx:instanceID>{escape(instance_id)}</orx:instanceID>'
        f'<orx:instanceName>{escape(run_id)}_{escape(case)}</orx:instanceName>{deprecated}</orx:meta>'
        f'<validation_run_id>{escape(run_id)}</validation_run_id>'
        f'<test_case_id>central_active_{escape(case)}</test_case_id>'
        f'<test_value>{escape(value)}</test_value>'
        f'<expected_value>CENTRAL-B</expected_value>'
        f'<change_reason>{escape(reason)}</change_reason>'
        f'<operator_note>Sentinel active validation harness</operator_note>'
        f'</data>'
    )
    return xml.encode("utf-8")


def _xml_field(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name:
            return str(element.text or "")
    return ""


def write_validation_artifacts(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write the JSON report and a reviewable PDF certificate."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report["artifacts"] = {
        "json": "validation_report.json",
        "pdf": "validation_certificate.pdf",
    }
    report_path = destination / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pdf_path = destination / "validation_certificate.pdf"
    try:
        _write_validation_pdf(report, pdf_path)
    except ModuleNotFoundError as error:
        if error.name != "reportlab":
            raise
        return {
            "json": str(report_path),
            "pdf": "",
            "pdf_error": "PDF certificate not generated: install the project dependencies with `python3 -m pip install -e .`",
        }
    return {"json": str(report_path), "pdf": str(pdf_path)}


def _write_validation_pdf(report: dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    styles = getSampleStyleSheet()
    title = ParagraphStyle("CertificateTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                           fontSize=18, leading=22, textColor=colors.HexColor("#17324D"), alignment=TA_LEFT)
    heading = ParagraphStyle("CertificateHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=colors.HexColor("#17324D"), spaceBefore=8)
    body = ParagraphStyle("CertificateBody", parent=styles["BodyText"], fontName="Helvetica",
                          fontSize=8.5, leading=11, textColor=colors.HexColor("#222222"))
    small = ParagraphStyle("CertificateSmall", parent=body, fontSize=7.2, leading=9)
    status = str(report.get("status", "unknown")).upper()
    summary = report.get("summary", {})
    project_id = report.get("project_id", "")
    created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report_hash = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=12 * mm,
                            leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    story: list[Any] = [
        Paragraph("Sentinel automated validation certificate", title),
        Spacer(1, 3 * mm),
        Paragraph(f"Project: <b>{project_id}</b> &nbsp;&nbsp; Status: <b>{status}</b> &nbsp;&nbsp; "
                  f"Generated: {created}", body),
        Paragraph(f"Checks: {summary.get('checks', 0)} &nbsp; Passed: {summary.get('passed', 0)} "
                  f"&nbsp; Failed: {summary.get('failed', 0)}", body),
        Spacer(1, 4 * mm),
        Paragraph("Certificate scope", heading),
        Paragraph("This certificate is the human-readable review view of the accompanying "
                  "validation_report.json. Central checks describe what the configured account "
                  "could observe or read from ODK Central. Sentinel checks describe Sentinel's "
                  "own deterministic identity, scope and configuration controls. It does not "
                  "certify host infrastructure, browser behavior, device behavior or MethodMesh "
                  "unless those checks are explicitly present.", body),
        Spacer(1, 3 * mm),
        Paragraph("Test results and evidence references", heading),
    ]
    table_data = [[Paragraph("Test", small), Paragraph("Component", small), Paragraph("Mode", small),
                   Paragraph("Result", small), Paragraph("Evidence", small), Paragraph("Detail", small)]]
    for check in report.get("checks", []):
        result = str(check.get("status", "")).upper()
        result_color = "#19733A" if result == "PASS" else "#A12828"
        evidence = check.get("evidence_ref", "validation_report.json")
        table_data.append([
            Paragraph(str(check.get("check_id", "")), small),
            Paragraph(str(check.get("component", "")), small),
            Paragraph(str(check.get("mode", "")), small),
            Paragraph(f'<font color="{result_color}"><b>{result}</b></font>', small),
            Paragraph(f'<link href="{evidence}"><u>{evidence}</u></link>', small),
            Paragraph(str(check.get("detail", "")), small),
        ])
    table = LongTable(table_data, repeatRows=1, colWidths=[27 * mm, 31 * mm, 23 * mm, 19 * mm, 61 * mm, 103 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A8B5C2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
    ]))
    story.append(table)
    def footer(canvas: Any, _document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5B6770"))
        canvas.drawString(12 * mm, 7 * mm, f"JSON report SHA-256: {report_hash}")
        canvas.drawRightString(285 * mm, 7 * mm, "JSON is authoritative; PDF is the review certificate")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
