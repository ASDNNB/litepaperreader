# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.0.0-dev | ✅ |
| < 1.0.0 | ❌ |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately by opening a [security advisory](https://github.com/ASDNNB/litepaperreader/security/advisories/new).

Please do **not** report security vulnerabilities through public GitHub issues.

## What to Include

- Type of issue (e.g., code injection, dependency vulnerability)
- Full paths of source file(s) related to the issue
- Steps to reproduce
- Proof of concept (if applicable)
- Impact assessment

## Response Timeline

- **24 hours**: Initial acknowledgment
- **7 days**: Assessment and mitigation plan
- **30 days**: Fix released (depending on complexity)

## Security Best Practices

1. **API Keys**: Use environment variables (e.g., `$OPENAI_API_KEY`), never hardcode
2. **Local-first**: LitePaperReader processes data locally by default
3. **File access**: The tool respects filesystem permissions; it only accesses files you explicitly provide
4. **Network**: Optional network features (web fetching, remote models) are opt-in only

## Dependencies

We use automated dependency scanning via GitHub Dependabot. Vulnerable dependencies are flagged and updated promptly.
