# Test-project run

Publish `docs/project_audit_sentinel_v1.xlsx` in the selected Central project,
give the Sentinel account read access to source forms and submit access to the
audit form, then create a local configuration file outside the repository:

```json
{
  "base_url": "https://central.example.org",
  "project_id": "123",
  "email": "your-central-email@example.org",
  "audit_form_id": "sentinel_project_audit",
  "audit_form_version": "1",
  "timestamp_policy": "preferred",
  "timestamp_url": "https://tsr.open-tsa.eu",
  "token_env": "ODK_CENTRAL_TOKEN"
}
```

With `email` present and no token environment variable set, Sentinel prompts
for the password without echoing it, creates a Central session, and keeps the
session token in memory for that run. It does not save the password or token.
Alternatively, set the named bearer token in the environment and run:

```sh
python -m sentinel_archive.cli /private/path/sentinel-project.json
```

The crawler excludes only the configured audit form itself, walks every other
form and retained submission version, and submits one audit record per version
plus one project checkpoint. It hashes the source XML in memory and submits
only hashes, references and Central metadata. It does not write raw data to
the local filesystem or copy source bundles into the audit form.

At the end of each run Sentinel creates a human-readable batch manifest,
hashes it, and sends only that hash to the configured RFC3161 TSA. With the
preferred policy, a TSA outage leaves the manifest attached and records
`manifest_created_not_timestamped`; with `required`, the run fails instead.
When successful, the audit record receives the TSA token and certificate as
attachments and stores the manifest hash, token hash and trusted time.

The first run should use a synthetic or dedicated test project. Confirm the
audit form opens in Enketo and that a second run reports no new versions before
using a production study.
