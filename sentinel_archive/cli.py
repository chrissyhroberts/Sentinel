from __future__ import annotations

import argparse
import json
from pathlib import Path

from .central import CentralClient, CentralConfig
from .crawler import ProjectAuditor


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit one ODK Central project into its Sentinel audit form")
    parser.add_argument("config", type=Path, help="JSON config containing base_url, project_id and audit_form_id")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    client = CentralClient(CentralConfig(
        base_url=config["base_url"],
        project_id=str(config["project_id"]),
        audit_form_id=config.get("audit_form_id", "sentinel_project_audit"),
        token_env=config.get("token_env", "ODK_CENTRAL_TOKEN"),
    ))
    summary = ProjectAuditor(client).run()
    print(json.dumps(summary.__dict__, indent=2))
