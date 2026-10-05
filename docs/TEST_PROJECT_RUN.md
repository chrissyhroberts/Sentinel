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

The first run should use a synthetic or dedicated test project. Confirm the
audit form opens in Enketo and that a second run reports no new versions before
using a production study.
