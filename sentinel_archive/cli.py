from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from .central import CentralClient, CentralConfig
from .crawler import ProjectAuditor
from .project import audit_instance_id
from .admin import run_admin_validation
from .validation import (run_active_validation, submit_active_validation_evidence,
                         validate_plan, validation_error, write_validation_artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit one ODK Central project into its Sentinel audit form")
    parser.add_argument("config", type=Path, help="JSON config containing base_url, project_id and audit_form_id")
    parser.add_argument("--plan-only", action="store_true", help="discover and print pending work without submitting anything")
    parser.add_argument("--debug", action="store_true", help="print progress and retry diagnostics to the terminal")
    parser.add_argument("--validate", action="store_true", help="run read-only automated validation checks")
    parser.add_argument("--validate-active", action="store_true",
                        help="create/edit synthetic validation data and verify the Central/Sentinel path")
    parser.add_argument("--admin-validate", action="store_true",
                        help="run the privileged, manually initiated administrative snapshot")
    parser.add_argument("--validation-output", type=Path, default=Path(".sentinel-local/validation"),
                        help="directory for validation_report.json and validation_certificate.pdf")
    parser.add_argument("--admin-output", type=Path, default=Path(".sentinel-local/admin-validation"),
                        help="directory for the privileged administrative snapshot and evidence package")
    parser.add_argument("--download-xml", nargs=3, metavar=("FORM_ID", "INSTANCE_ID", "OUTPUT"),
                        help="download one Central submission XML for diagnostics")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    central_config = CentralConfig(
        base_url=config["base_url"],
        project_id=str(config["project_id"]),
        audit_form_id=config.get("audit_form_id", "sentinel_project_audit"),
        audit_form_version=str(config.get("audit_form_version", "1")),
        token_env=config.get("token_env", "ODK_CENTRAL_TOKEN"),
        timestamp_policy=config.get("timestamp_policy", "preferred"),
        timestamp_url=config.get("timestamp_url", "https://tsr.open-tsa.eu"),
        server_audit_start=config.get("server_audit_start", ""),
        server_audit_enabled=bool(config.get("server_audit_enabled", False)),
        validation_form_ids=tuple(str(value) for value in config.get("validation_form_ids", [])),
        admin_project_ids=tuple(str(value) for value in config.get("admin_project_ids", [])),
        admin_audit_start=str(config.get("admin_audit_start", "")),
        admin_audit_end=str(config.get("admin_audit_end", "")),
        admin_host_snapshot_path=str(config.get("admin_host_snapshot_path", "")),
        admin_assignment_roles=tuple(str(value) for value in config.get(
            "admin_assignment_roles", ["manager", "viewer", "dataCollector"])),
    )
    if args.admin_validate:
        email = config.get("admin_email")
        if not email:
            raise SystemExit("--admin-validate requires admin_email in the Sentinel config")
        password = getpass.getpass(f"Central administrator password for {email}: ")
        client = CentralClient.login(central_config, email, password, debug=args.debug)
    else:
        email = config.get("email")
        stored_password = config.get("password") or (
            os.environ.get(str(config.get("password_env"))) if config.get("password_env") else None
        )
        if email and not os.environ.get(central_config.token_env):
            password = stored_password or getpass.getpass(f"Central password for {email}: ")
            client = CentralClient.login(central_config, email, password, debug=args.debug)
        else:
            client = CentralClient(central_config, debug=args.debug)
    auditor = ProjectAuditor(client)
    if args.download_xml:
        form_id, instance_id, output = args.download_xml
        Path(output).write_bytes(client.submission_xml(form_id, instance_id))
        print(output)
        return
    if args.admin_validate:
        print(json.dumps(run_admin_validation(client, args.admin_output), indent=2))
        return
    if args.validate_active:
        report = run_active_validation(client)
        artifacts = write_validation_artifacts(report, args.validation_output)
        audit_id = submit_active_validation_evidence(client, report, artifacts)
        print(json.dumps({"report": report, "artifacts": artifacts,
                          "audit_record": audit_id}, indent=2))
        return
    try:
        plan = auditor.plan()
    except Exception as error:
        if args.validate:
            report = validation_error(central_config.project_id, error)
            artifacts = write_validation_artifacts(report, args.validation_output)
            print(json.dumps({"report": report, "artifacts": artifacts}, indent=2))
            return
        raise
    if args.validate:
        report = validate_plan(client, plan)
        artifacts = write_validation_artifacts(report, args.validation_output)
        print(json.dumps({"report": report, "artifacts": artifacts}, indent=2))
        return
    pending = [task for task in plan.tasks if audit_instance_id(
        client.config.project_id, task[1], task[2], task[3]) not in plan.existing_audit_ids]
    print(json.dumps({
        "project_id": client.config.project_id,
        "forms_to_audit": len(plan.forms),
        "form_versions_discovered": sum(task[0] == "form_version" for task in plan.tasks),
        "submission_versions_discovered": sum(task[0] == "submission_version" for task in plan.tasks),
        "pending_records": len(pending),
        "existing_audit_records": len(plan.existing_audit_ids),
    }, indent=2))
    if not args.plan_only:
        print(json.dumps(auditor.run(plan).__dict__, indent=2))


if __name__ == "__main__":
    main()
