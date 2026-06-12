 # Security Policy

 ## Supported Versions

 As LitePaperReader is in active development (pre-1.0), security patches will be
 applied to the latest commit on the `master` branch.

 | Version | Supported |
 |---------|-----------|
 | 1.0.0-dev (master) | ✅ |
 | Older releases | ❌ |

 ## Reporting a Vulnerability

 We take security seriously. If you discover a security vulnerability, please:

 1. **Do not** open a public issue.
 2. Email the maintainers or open a [private security advisory](https://github.com/ASDNNB/litepaperreader/security/advisories/new).
 3. Provide a clear description of the vulnerability and steps to reproduce.

 We will acknowledge receipt within 48 hours and strive to release a fix within
 7 days of confirmation.

 ## Security Considerations

 - LitePaperReader processes documents from filesystem, git, and web sources.
   Always validate the origin of input documents before processing.
 - The MCP server listens on localhost by default. If exposing to a network,
   use a reverse proxy with authentication.
 - API keys for OpenAI and other LLM providers are handled via environment
   variables or runtime parameters — never hardcode credentials.
 - Watch mode reads files from the filesystem. Ensure the watched directory
   only contains trusted documents.
