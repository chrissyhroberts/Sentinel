import json
import unittest
import zipfile
from pathlib import Path

from sentinel_archive.crawler import ProjectAuditor
from sentinel_archive.validation import (run_active_validation,
                                         submit_active_validation_evidence,
                                         validate_plan, write_validation_artifacts)


class FakeConfig:
    project_id = "16"
    audit_form_id = "sentinel_project_audit"
    audit_form_version = "5"
    timestamp_policy = "disabled"
    timestamp_url = "https://tsa.example.invalid/tsa"
    validation_form_ids = ("sentinel_validation_central",)


class FakeClient:
    config = FakeConfig()

    def forms(self):
        return [{"xmlFormId": "trial"}, {"xmlFormId": "sentinel_project_audit"}]

    def project(self):
        return {"id": 16, "name": "Test project", "archived": False}

    def submissions(self, form_id):
        if form_id == "sentinel_project_audit":
            return []
        return [{"instanceId": "uuid:one"}]

    def form_versions(self, form_id):
        return [{"version": "2026-10-05"}]

    def form_version_bytes(self, form_id, version, extension):
        return (b"<h:html xmlns:h='http://www.w3.org/1999/xhtml'/>") if extension == "xml" else b"xlsx"

    def versions(self, form_id, instance_id):
        return [{"instanceId": "uuid:v1", "createdAt": "2026-10-05T10:00:00Z", "submitterId": "user-1"}]

    def version_xml(self, form_id, instance_id, version_id):
        return b"<data><meta><instanceID>uuid:one</instanceID></meta></data>"

    def audits(self, form_id, instance_id):
        return [{"action": "submission.update", "details": {
            "versionId": "uuid:v1", "actionNotes": "corrected source value"
        }}]

    def comments(self, form_id, instance_id):
        return [{"body": "unlinked submission comment"}]

    def actor_email(self, actor_id):
        return "user@example.org" if actor_id == "user-1" else ""

    def diffs(self, form_id, instance_id):
        return {"uuid:v1": [{"path": ["answer"], "old": "old", "new": "new"}]}

    def version_attachments(self, form_id, instance_id, version_id):
        return [{"name": "audit.csv", "exists": True}]

    def attachment_bytes(self, form_id, instance_id, version_id, filename):
        return b"event,node,change-reason\nchange reason,,corrected source value\n"


class FakeSink:
    def __init__(self):
        self.submissions = []

    def submit(self, form_id, xml, attachments):
        self.submissions.append((form_id, xml, attachments))


class ActiveFakeClient:
    class Config:
        project_id = "16"
        audit_form_id = "sentinel_project_audit"
        audit_form_version = "1"
        validation_form_ids = ("sentinel_validation_central",)

    config = Config()

    def __init__(self):
        self.current = None
        self.initial = None
        self.updated = False
        self.submitted = []

    def create_validation_submission(self, form_id, xml, *, device_id):
        self.initial = xml
        self.current = xml
        return {"instanceId": "uuid:active-fake"}

    def update_validation_submission(self, form_id, instance_id, xml, *, action_notes):
        self.current = xml
        self.updated = True
        return {"instanceId": "uuid:active-fake-edited"}

    def form_versions(self, form_id):
        return [{"version": "1"}]

    def form_version_bytes(self, form_id, version, extension):
        return b"<h:html xmlns:h='http://www.w3.org/1999/xhtml'/>"

    def submission(self, form_id, instance_id):
        return {"instanceId": instance_id, "updatedAt": "2026-10-05T10:00:00Z"}

    def comments(self, form_id, instance_id):
        return []

    def submission_xml(self, form_id, instance_id):
        return self.current

    def version_xml(self, form_id, instance_id, version_id):
        return self.initial if version_id == "uuid:active-fake" else self.current

    def version_attachments(self, form_id, instance_id, version_id):
        return []

    def versions(self, form_id, instance_id):
        if not self.updated:
            return [{"instanceId": "uuid:active-fake"}]
        return [{"instanceId": "uuid:active-fake"}, {"instanceId": "uuid:active-fake-edited"}]

    def diffs(self, form_id, instance_id):
        return {"uuid:active-fake-edited": [{"path": ["test_value"], "old": "CENTRAL-A", "new": "CENTRAL-B"}]}

    def audits(self, form_id, instance_id):
        return [{"action": "submission.update", "details": {
            "actionNotes": "Sentinel validation changed test_value from CENTRAL-A to CENTRAL-B",
            "actorId": "validation-user",
        }}]

    def submit(self, form_id, xml, attachments):
        self.submitted.append((form_id, xml, attachments))


class CrawlerTests(unittest.TestCase):
    def test_active_validation_exercises_synthetic_create_edit_and_evidence(self):
        client = ActiveFakeClient()
        report = run_active_validation(client)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"], {"checks": 20, "passed": 20, "failed": 0})
        self.assertEqual(report["mode"], "active_synthetic_validation")
        self.assertTrue(all(check["evidence_ref"].startswith("evidence_") for check in report["checks"]))
        self.assertEqual(
            {check["check_id"] for check in report["checks"]},
            {
                "central_active_create", "central_active_form_definition", "central_active_edit",
                "central_active_version_records", "central_active_version_identity",
                "central_active_original_version_readback", "central_active_attachment_inventory",
                "central_active_diff", "central_active_diff_structure", "central_active_reason",
                "central_active_audit_trail", "central_active_actor_attribution",
                "central_active_metadata_read", "central_active_comments_read",
                "central_active_submission_identity", "central_active_xml_well_formed",
                "sentinel_active_hash_change", "sentinel_active_deterministic_id",
                "sentinel_active_evidence_capture", "sentinel_active_synthetic_scope",
            },
        )
        with self.subTest("audit evidence"):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as directory:
                artifacts = write_validation_artifacts(report, directory)
                audit_id = submit_active_validation_evidence(client, report, artifacts)
                self.assertTrue(audit_id.startswith("uuid:sentinel-"))
                self.assertEqual(len(client.submitted), 1)
                expected_attachments = {"validation_report.json", "evidence_package.zip"}
                if artifacts.get("pdf"):
                    expected_attachments.add("validation_certificate.pdf")
                self.assertEqual(set(client.submitted[0][2]), expected_attachments)
                self.assertIn(b"<record_type>validation_certificate</record_type>", client.submitted[0][1])
                with zipfile.ZipFile(artifacts["evidence_package"]) as package:
                    members = set(package.namelist())
                self.assertTrue(any(name.endswith("/evidence_manifest.json") for name in members))
                self.assertTrue(any(name.endswith("/central/form_definition.xml") for name in members))
                self.assertTrue(any(name.endswith("/central/created_submission.xml") for name in members))
                self.assertTrue(any(name.endswith("/central/original_version.xml") for name in members))
                self.assertTrue(any(name.endswith("/central/diffs.json") for name in members))

    def test_read_only_validation_separates_central_and_sentinel_checks(self):
        client = FakeClient()
        plan = ProjectAuditor(client).plan()
        report = validate_plan(client, plan)
        self.assertEqual(report["status"], "passed")
        self.assertIn("ODK Central", report["components"])
        self.assertIn("Sentinel", report["components"])
        self.assertTrue(all(check["status"] == "pass" for check in report["checks"]))
        with self.subTest("read-only evidence package"):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as directory:
                artifacts = write_validation_artifacts(report, directory)
                self.assertTrue(all(check["evidence_ref"].startswith("evidence_")
                                    for check in json.loads(
                                        Path(artifacts["json"]).read_text(encoding="utf-8")).get("checks", [])))
                with zipfile.ZipFile(artifacts["evidence_package"]) as package:
                    members = set(package.namelist())
                self.assertTrue(any(name.endswith("/central/project.json") for name in members))
                self.assertTrue(any(name.endswith("/sentinel/plan.json") for name in members))

    def test_validation_forms_are_excluded_from_source_scope(self):
        client = FakeClient()
        client.config.validation_form_ids = ("trial",)
        plan = ProjectAuditor(client).plan()
        self.assertEqual(plan.forms, ())
        self.assertEqual(plan.tasks, ())

    def test_project_scope_and_resume_record(self):
        sink = FakeSink()
        auditor = ProjectAuditor(FakeClient(), sink)
        plan = auditor.plan()
        self.assertEqual(len(plan.tasks), 2)
        summary = auditor.run(plan)
        self.assertEqual(summary.forms_seen, 1)
        self.assertEqual(summary.versions_submitted, 1)
        self.assertEqual(summary.form_versions_submitted, 1)
        self.assertEqual(len(sink.submissions), 4)
        submission = [item for item in sink.submissions if b"linked_collect_audit" in item[1]][0]
        self.assertIn(b"<record_type>submission_edit</record_type>", submission[1])
        self.assertIn(b"<central_actor_id>user@example.org</central_actor_id>", submission[1])
        self.assertIn(b"Changed: /answer: old -&gt; new | Reason: corrected source value", submission[1])
        manifest = [item for item in sink.submissions if b"<record_type>run_timestamp_manifest</record_type>" in item[1]][0]
        self.assertEqual(set(manifest[2]), {
            "timestamp_manifest.json", "project_health_snapshot.json",
            "project_user_roles_snapshot.json", "validation_report.json",
        })
        self.assertIn(b"submission_edit", manifest[2]["timestamp_manifest.json"])
        self.assertIn(b'"chain": {\n    "status": "genesis"', manifest[2]["timestamp_manifest.json"])
        self.assertIn(b"<timestamp_manifest>timestamp_manifest.json</timestamp_manifest>", manifest[1])
        self.assertIn(b"<timestamp_token></timestamp_token>", manifest[1])
        self.assertIn(b'<data id="sentinel_project_audit" version="5"', submission[1])
        self.assertIn(b"<orx:meta><orx:instanceID>", submission[1])
        self.assertEqual(submission[2], {})
        self.assertIn(b"<project_health_snapshot>project_health_snapshot.json</project_health_snapshot>", manifest[1])
        self.assertIn(b"<project_user_roles_snapshot>project_user_roles_snapshot.json</project_user_roles_snapshot>", manifest[1])
        self.assertIn(b"<validation_report>validation_report.json</validation_report>", manifest[1])
        self.assertIn(b'"retained_versions": 1', manifest[2]["project_health_snapshot.json"])
        self.assertIn(b'project_user_roles_snapshot.v1', manifest[2]["project_user_roles_snapshot.json"])
        self.assertIn(b'"status": "passed_with_warnings"', manifest[2]["validation_report.json"])


if __name__ == "__main__":
    unittest.main()
