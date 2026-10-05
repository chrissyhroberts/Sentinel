from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from .central import CentralClient, CentralConfig
from .crawler import ProjectAuditor
from .project import audit_instance_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit one ODK Central project into its Sentinel audit form")
    parser.add_argument("config", type=Path, help="JSON config containing base_url, project_id and audit_form_id")
    parser.add_argument("--plan-only", action="store_true", help="discover and print pending work without submitting anything")
    parser.add_argument("--debug", action="store_true", help="print progress and retry diagnostics to the terminal")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    central_config = CentralConfig(
        base_url=config["base_url"],
        project_id=str(config["project_id"]),
        audit_form_id=config.get("audit_form_id", "sentinel_project_audit"),
        audit_form_version=str(config.get("audit_form_version", "1")),
        token_env=config.get("token_env", "ODK_CENTRAL_TOKEN"),
    )
    email = config.get("email")
    if email and not os.environ.get(central_config.token_env):
        password = getpass.getpass(f"Central password for {email}: ")
        client = CentralClient.login(central_config, email, password, debug=args.debug)
    else:
        client = CentralClient(central_config, debug=args.debug)
    auditor = ProjectAuditor(client)
    plan = auditor.plan()
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
