# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x (BSL release line) | Yes |
| 0.x pre-release | Best effort |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email **security@giggso.com** (or the GitHub security advisory flow on
[giggsoinc/aryx](https://github.com/giggsoinc/aryx)) with:

- Description of the issue
- Steps to reproduce
- Affected version / commit
- Impact assessment if known

We aim to acknowledge reports within 5 business days.

## Safe defaults for production

If you expose Aryx beyond localhost:

- Set `ARYX_API_AUTH=required` and issue API keys
- Disable open MCP auth (`ARYX_MCP_AUTH_OPTIONAL=0`) and mint MCP tokens
- Do not publish Postgres/FalkorDB ports to the public internet
- Change default database passwords from compose samples

See project docs for deployment guidance.
