# Test-project run

Publish `docs/sentinel_project_audit_v1.xml` in the selected Central project,
give the Sentinel account read access to source forms and submit access to the
audit form, then create a local configuration file outside the repository:

```json
{
  "base_url": "https://central.example.org",
  "project_id": "123",
  "audit_form_id": "sentinel_project_audit",
  "token_env": "ODK_CENTRAL_TOKEN"
}
```

Set the bearer token in the named environment variable and run:

```sh
python -m sentinel_archive.cli /private/path/sentinel-project.json
```

The crawler excludes only the configured audit form itself, walks every other
form and retained submission version, and submits one audit record per version
plus one project checkpoint. It keeps the source XML, Central audit data,
comments and diffs in memory while creating one exact source bundle. It does
not write raw data to the local filesystem.

The first run should use a synthetic or dedicated test project. Confirm the
audit form accepts the binary source bundle and that a second run reports no
new versions before using a production study.
