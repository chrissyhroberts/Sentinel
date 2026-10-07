# Admin Sentinel procedure

Admin Sentinel is the privileged, manually initiated companion to the normal
project Sentinel run. It is intended for an occasional review, such as a
monthly system-administration check, not for every source-data crawl.

## Account separation

The normal account is configured as `email` and may use `password_env` or a
local `password`. The administrator account is configured separately as
`admin_email`. The admin password is always entered at the terminal when the
admin command is run.

Example local-only configuration:

```json
{
  "base_url": "https://central.example.org",
  "project_id": "239",
  "audit_form_id": "audit_001",
  "audit_form_version": "4",
  "email": "regular@example.org",
  "password_env": "SENTINEL_CENTRAL_PASSWORD",
  "admin_email": "administrator@example.org",
  "admin_project_ids": ["239"],
  "admin_audit_start": "",
  "admin_audit_end": "",
  "admin_host_snapshot_path": ""
}
```

Keep the file in `.sentinel-local/`; it is ignored by Git. Never commit a
password or session token.

## Run

```sh
python3 -m sentinel_archive.cli .sentinel-local/sentinel.config --admin-validate
```

Use `--admin-output` to choose another local output directory. A blank audit
window means the previous 31 days ending at the current UTC time. The command
is read-only with respect to Central source data and configuration, but submits
one administrative snapshot to the configured audit form.

## What is collected

The report and evidence package contain the authenticated administrator
identity, configured project scope, visible projects, project assignments,
server roles, server-wide assignments, and the time-scoped Central audit feed
filtered to the configured projects and their assigned actors. Relevant events
include project-user logins and user, assignment, form and project lifecycle
events exposed by Central. Available Central system observations and an
optional host snapshot are included too.

The audit-form record type is `admin_platform_snapshot`. Its attachments use
the existing universal fields `platform_snapshot`, `platform_snapshot_pdf` and
`evidence_package`.

## Host metrics and API limits

The Central API can provide application observations and server audit events,
but ordinary API access does not expose the host's disk space, uptime, CPU,
memory or backup state. Those values must be supplied by a separately
controlled host-side procedure if required. The optional JSON file can look
like:

```json
{
  "central_version": "v2026.x.y",
  "uptime_seconds": 123456,
  "disk_space": {"available_bytes": 1234567890, "total_bytes": 9876543210},
  "captured_at": "2026-10-07T09:00:00Z",
  "source": "approved host snapshot procedure"
}
```

An absent host snapshot is reported as a warning, not silently treated as a
measurement. A failed server-audit read is reported as a failed admin check.

## Outputs and review

The default output directory is `.sentinel-local/admin-validation/`:

- `admin_snapshot.json` — machine-readable snapshot and check results;
- `admin_snapshot.pdf` — human-readable review copy;
- `evidence_package.zip` — raw observations, supplied host input, snapshot and
  SHA-256 evidence manifest.

The submitted audit-form record links the same JSON, PDF and ZIP evidence. This
snapshot records what the administrator account could observe during the
selected window; it is not a substitute for infrastructure backup,
monitoring or disaster-recovery records.

The relevant Central capabilities are described in the [System Endpoints],
[Server Audit Logs], [Accounts and Users] and [Project Management] references.

[System Endpoints]: https://docs.getodk.org/central-api-system-endpoints/
[Server Audit Logs]: https://docs.getodk.org/central-server-audits/
[Accounts and Users]: https://docs.getodk.org/central-api-accounts-and-users/
[Project Management]: https://docs.getodk.org/central-api-project-management/
