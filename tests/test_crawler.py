import json
import unittest

from sentinel_archive.crawler import ProjectAuditor


class FakeConfig:
    project_id = "16"
    audit_form_id = "sentinel_project_audit"
    timestamp_policy = "disabled"
    timestamp_url = "https://tsa.example.invalid/tsa"


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


class CrawlerTests(unittest.TestCase):
    def test_project_scope_and_resume_record(self):
        sink = FakeSink()
        auditor = ProjectAuditor(FakeClient(), sink)
        plan = auditor.plan()
        self.assertEqual(len(plan.tasks), 2)
        summary = auditor.run(plan)
        self.assertEqual(summary.forms_seen, 1)
        self.assertEqual(summary.versions_submitted, 1)
        self.assertEqual(summary.form_versions_submitted, 1)
        self.assertEqual(len(sink.submissions), 6)
        submission = [item for item in sink.submissions if b"linked_collect_audit" in item[1]][0]
        self.assertIn(b"<record_type>submission_edit</record_type>", submission[1])
        self.assertIn(b"<central_actor_id>user@example.org</central_actor_id>", submission[1])
        self.assertIn(b"Changed: /answer: old -&gt; new | Reason: corrected source value", submission[1])
        manifest = [item for item in sink.submissions if b"<record_type>run_timestamp_manifest</record_type>" in item[1]][0]
        self.assertEqual(set(manifest[2]), {"timestamp_manifest.json"})
        self.assertIn(b"submission_edit", manifest[2]["timestamp_manifest.json"])
        self.assertIn(b'"chain": {\n    "status": "genesis"', manifest[2]["timestamp_manifest.json"])
        self.assertIn(b"<timestamp_manifest>timestamp_manifest.json</timestamp_manifest>", manifest[1])
        self.assertIn(b"<timestamp_token></timestamp_token>", manifest[1])
        self.assertIn(b'<data id="sentinel_project_audit" version="1"', submission[1])
        self.assertIn(b"<orx:meta><orx:instanceID>", submission[1])
        self.assertEqual(submission[2], {})
        certificate = [item for item in sink.submissions if b"<record_type>validation_certificate</record_type>" in item[1]][0]
        self.assertEqual(set(certificate[2]), {"validation_certificate.json"})
        self.assertIn(b'"status": "passed_with_warnings"', certificate[2]["validation_certificate.json"])
        snapshot = [item for item in sink.submissions if b"<record_type>project_health_snapshot</record_type>" in item[1]][0]
        self.assertEqual(set(snapshot[2]), {"platform_snapshot.json"})
        self.assertIn(b'"retained_versions": 1', snapshot[2]["platform_snapshot.json"])


if __name__ == "__main__":
    unittest.main()
