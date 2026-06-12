# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report them by emailing **cagri@mpospirit.com** with the subject line `[TetherDust Security] <short description>`.

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept or detailed instructions)
- Affected versions/components
- Any suggested fix, if you have one

## Disclosure policy

- Please give me reasonable time to investigate and release a fix before any public disclosure.
- I will coordinate a disclosure date with you once a fix is ready.
- If you follow responsible disclosure, I will credit you in the release notes (unless you prefer to remain anonymous).

## Scope

The following are in scope:

- Authentication and authorization bypasses (role checks, `is_admin_role`, staff flag)
- SQL injection or read-only enforcement bypass in `mcp_server/utils/db_service.py`
- Credential exposure (Fernet-encrypted database passwords, agent API keys/tokens)
- Cross-site scripting (XSS) in the chat or admin console
- Server-side request forgery (SSRF) via database connections or MCP server URLs
- Remote code execution via agent gateways or MCP tool execution
- Insecure direct object references in report, dashboard, or tether access

The following are **out of scope**:

- Vulnerabilities in self-hosted infrastructure the user controls (OS, Docker host, network)
- Denial-of-service attacks requiring authenticated access
- Issues in third-party dependencies (report those upstream; let me know if TetherDust is the vector)
- Findings from automated scanners without a working proof of concept

## Supported versions

Only the latest release is actively maintained. Security fixes are not backported to older versions.
