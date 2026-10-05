import json
import unittest

from sentinel_archive.crawler import ProjectAuditor


class FakeConfig:
    project_id = "16"
    audit_form_id = "sentinel_project_audit"


class FakeClient:
    config = FakeConfig()

    def forms(self):
        return [{"xmlFormId": "trial"}, {"xmlFormId": "sentinel_project_audit"}]

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

    def version_metadata(self, form_id, instance_id, version_id):
        return {"attachments": [{"filename": "audit.csv", "exists": True}]}

    def attachment_bytes(self, form_id, instance_id, version_id, filename):
        return b"event,timestamp\nform start,2026-10-05T10:00:00Z\n"

    def audits(self, form_id, instance_id):
        return [{"action": "submission.create", "versionId": "uuid:v1"}]

    def comments(self, form_id, instance_id):
        return [{"versionId": "uuid:v1", "body": "corrected source value"}]

    def diffs(self, form_id, instance_id):
        return {"versions": []}


class FakeSink:
    def __init__(self):
        self.submissions = []

    def submit(self, form_id, xml, attachments):
        self.submissions.append((form_id, xml, attachments))


class CrawlerTests(unittest.TestCase):
    def test_project_scope_and_resume_record(self):
        sink = FakeSink()
        summary = ProjectAuditor(FakeClient(), sink).run()
        self.assertEqual(summary.forms_seen, 1)
        self.assertEqual(summary.versions_submitted, 1)
        self.assertEqual(summary.form_versions_submitted, 1)
        self.assertEqual(len(sink.submissions), 3)
        submission = [item for item in sink.submissions if b"linked_central_comment" in item[1]][0]
        self.assertIn("source_bundle.zip", submission[2])
        bundle = submission[2]["source_bundle.zip"]
        self.assertIn(b"submission.xml", bundle)
        self.assertIn(b"attachments/audit.csv", bundle)


if __name__ == "__main__":
    unittest.main()
