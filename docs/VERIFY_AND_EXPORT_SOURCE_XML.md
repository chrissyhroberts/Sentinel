# Verify and export Central source XML

This procedure provides an independent check of Sentinel's source hash and a
complete XML export of retained source records. It uses ODK Central's API and
does not modify Central data.

## 1. Verify one submission or edit

### Information required

Read these values from the Sentinel audit-form record:

```text
project_id
source_form_id
source_instance_id
source_version_id
source_content_sha256
```

For an original submission, `source_instance_id` and `source_version_id` will
normally be the same. For an edit, `source_version_id` identifies the retained
Central version that must be downloaded.

### Download the exact version

The version-specific endpoint is:

```text
GET /v1/projects/{project_id}/forms/{source_form_id}/submissions/{source_instance_id}/versions/{source_version_id}.xml
```

On macOS, with an existing Central API session token held in the environment:

```sh
export ODK_CENTRAL_TOKEN='use-a-session-token-here'

curl --fail --silent --show-error \
  -H "Authorization: Bearer ${ODK_CENTRAL_TOKEN}" \
  -H 'Accept: application/xml' \
  --output source-version.xml \
  'https://central.example.org/v1/projects/239/forms/dummy_example_crf/submissions/uuid%3Ae4e02bbb-68b8-443d-92ca-8b05a257a32a/versions/uuid%3A1d00edd6-14ba-4285-b1a1-3232e8ad5683.xml'
```

Do not place a password in the command line or commit a token. Replace the
example host, project, form, instance and version values with the values from
the Sentinel record.

### Hash the raw response

```sh
shasum -a 256 source-version.xml
```

The resulting digest must exactly equal `source_content_sha256` in Sentinel.
Do not parse, pretty-print, normalise line endings or reserialize the XML
before hashing. A hash match means that the Central version downloaded is the
exact byte sequence Sentinel recorded.

The endpoint is version-specific: downloading the current submission XML is
not sufficient to verify an older edit.

## 2. Download every retained original XML

An ODK Central CSV export is not a substitute for the original XML. To retain
the original source representation, enumerate the Central objects and download
the version-specific XML for each original submission.

### Enumeration sequence

For the configured project:

1. List forms:

   ```text
   GET /v1/projects/{project_id}/forms
   ```

2. For each source form, list submissions:

   ```text
   GET /v1/projects/{project_id}/forms/{xml_form_id}/submissions
   ```

3. For each logical submission, list retained versions:

   ```text
   GET /v1/projects/{project_id}/forms/{xml_form_id}/submissions/{instance_id}/versions
   ```

4. Download the original version where `version.instanceId` equals the
   logical submission `instanceId`:

   ```text
   GET /v1/projects/{project_id}/forms/{xml_form_id}/submissions/{instance_id}/versions/{version_id}.xml
   ```

5. Hash every downloaded file and retain a manifest containing the Central
   identifiers and digest.

### Recommended export manifest

Use one row per downloaded XML:

```json
{
  "project_id": "239",
  "form_id": "dummy_example_crf",
  "instance_id": "uuid:e4e02bbb-68b8-443d-92ca-8b05a257a32a",
  "version_id": "uuid:e4e02bbb-68b8-443d-92ca-8b05a257a32a",
  "kind": "original_submission",
  "sha256": "...",
  "downloaded_at": "2026-10-06T00:00:00Z"
}
```

For a complete retained history rather than originals only, download every
version returned by the `/versions` endpoint and set `kind` to
`original_submission` or `submission_edit` according to the version ID.

### Scope and limitations

- This exports records retained by Central at the time of enumeration.
- A submission or form permanently purged by Central cannot be downloaded.
- Deleted-but-not-purged forms may be discoverable through the Central deleted
  forms option, subject to the account's permissions and Central version.
- Keep the export in the approved controlled archive or inspection workspace;
  do not create an unapproved local research dataset.

## 3. Compare against Sentinel

For each XML in the export, compare its SHA-256 with the corresponding
Sentinel `source_content_sha256`. Investigate any of the following:

- a missing Central version;
- a missing Sentinel record;
- a hash mismatch;
- duplicate or unexpected version identifiers;
- a Sentinel manifest-chain warning.

The Sentinel audit form remains an integrity index. Central remains the source
repository for the original XML and its retained versions.

## References

- [ODK Central submission management API](https://docs.getodk.org/central-api-submission-management/)
- [ODK Central authentication](https://docs.getodk.org/central-api-authentication/)
