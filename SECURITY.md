# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 4.0.x | Yes |
| 3.x | Migration support only |
| Earlier | No |

## Reporting a vulnerability

Do not report vulnerabilities, credentials, customer data or exploit details in a public issue.

Until a dedicated security mailbox is published, contact the repository owner privately through the verified GitHub account. Include:

- affected version and component;
- reproducible steps;
- expected and observed behavior;
- impact assessment;
- suggested mitigation, when available.

Please allow a reasonable remediation window before public disclosure.

## Operational boundaries

The distributed runtime is shadow-first. Do not enable external connectors or production actions without an explicit policy, isolated credentials, rollback controls, audit logging and human approval appropriate to the risk.

## Secrets

Never commit `.env` files, API keys, JWT secrets, database passwords, private keys, customer datasets or production backups. Use GitHub Environments/Secrets or an external secret manager.
