import json
import tempfile
import unittest
from pathlib import Path

from sentinel_archive import ArchiveStore, VersionInput


class ArchiveTests(unittest.TestCase):
    def test_archives_exact_submission_audit_and_edit_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "submission.xml"
            audit = root / "audit.csv"
            attachment = root / "photo.jpg"
            source.write_bytes(b"<data><instanceID>uuid:1</instanceID><value>A</value></data>")
            audit.write_bytes(b"event,formhierarchy\nform start,/data\n")
            attachment.write_bytes(b"attachment")

            record = ArchiveStore(root / "archive").archive_version(VersionInput(
                form_id="trial_form",
                instance_id="uuid:1",
                version_id="v1",
                submission=source,
                audit_trail=audit,
                attachments=(attachment,),
                central_metadata={"createdAt": "2026-10-05T10:00:00Z", "actor": "site-user"},
                change_events=({"reason": "original submission"},),
                timestamp={"status": "rfc3161_verified", "time": "2026-10-05T10:01:00Z"},
            ))

            version_dir = root / "archive/forms/trial_form/instances/uuid_1/versions/v1"
            self.assertEqual((version_dir / "submission.xml").read_bytes(), source.read_bytes())
            self.assertEqual(record["canonical_reconstruction"], "not_performed")
            self.assertEqual(record["previous_attestation_hash"], None)
            index = json.loads((version_dir.parent.parent / "audit_record.json").read_text())
            self.assertEqual(index["versions"][0]["version_id"], "v1")
            self.assertIn("original submission", (version_dir.parent.parent / "audit_record.html").read_text())


if __name__ == "__main__":
    unittest.main()
