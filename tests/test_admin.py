import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from sentinel_archive.admin import run_admin_validation


class AdminConfig:
    project_id = "239"
    audit_form_id = "audit_001"
    audit_form_version = "5"
    admin_project_ids = ("239",)
    admin_audit_start = "2026-10-01T00:00:00Z"
    admin_audit_end = "2026-10-07T00:00:00Z"
    admin_host_snapshot_path = ""
    admin_assignment_roles = ("manager", "viewer")


class AdminFakeClient:
    config = AdminConfig()

    def __init__(self):
        self.submitted = []

    def user(self, user_id):
        return {"id": "admin-1", "email": "admin@example.org"}

    def projects(self):
        return [{"id": 239, "name": "Validation project"}]

    def project_assignments(self, project_id, role_id):
        return [{"id": "user-1", "email": "user@example.org", "role": role_id}]

    def roles(self):
        return [{"id": "admin", "name": "Server Administrator"}]

    def assignments(self):
        return [{"userId": "admin-1", "roleId": "admin"}]

    def server_audits(self, *, start, end):
        return [
            {"action": "user.session.create", "actorId": "user-1", "projectId": 239},
            {"action": "user.session.create", "actorId": "unrelated-user", "projectId": 999},
        ]

    def system_config(self, key):
        return {"key": key, "enabled": True}

    def analytics_preview(self):
        return {"status": "available"}

    def submit(self, form_id, xml, attachments):
        self.submitted.append((form_id, xml, attachments))


class AdminValidationTests(unittest.TestCase):
    def test_admin_snapshot_is_scoped_and_submitted_with_evidence(self):
        client = AdminFakeClient()
        with tempfile.TemporaryDirectory() as directory:
            result = run_admin_validation(client, directory)
            snapshot = result["snapshot"]
            self.assertEqual(snapshot["status"], "passed_with_warnings")
            self.assertEqual(snapshot["central"]["relevant_audit_events"], 1)
            self.assertEqual(snapshot["audit_window"]["start"], "2026-10-01T00:00:00Z")
            self.assertTrue(Path(result["artifacts"]["pdf"]).exists())
            with zipfile.ZipFile(result["artifacts"]["evidence_package"]) as package:
                members = set(package.namelist())
                self.assertTrue(any(name.endswith("/central/server_audits.json") for name in members))
                self.assertTrue(any(name.endswith("/central/relevant_audits.json") for name in members))
                self.assertTrue(any(name.endswith("/evidence_manifest.json") for name in members))
            self.assertEqual(len(client.submitted), 1)
            form_id, xml, attachments = client.submitted[0]
            self.assertEqual(form_id, "audit_001")
            self.assertIn(b"<record_type>admin_platform_snapshot</record_type>", xml)
            self.assertEqual(set(attachments), {
                "admin_platform_snapshot.json", "admin_platform_snapshot.pdf", "evidence_package.zip",
            })
            written = json.loads(Path(result["artifacts"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(written["summary"]["warnings"], 1)


if __name__ == "__main__":
    unittest.main()
