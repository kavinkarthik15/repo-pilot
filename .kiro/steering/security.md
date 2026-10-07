# RepoPilot — Security and Privacy Rules

These rules are mandatory. No feature, optimisation, or convenience justification overrides them.

## Secret and Credential Protection

- **Never include the contents of secret files in any output.** If a rule fires on a file suspected to contain credentials (e.g., `.env`, `*.pem`, `credentials.json`), the finding must reference the filename and path only — never the file's contents.
- **Never include environment variable values in reports.** Variable names may appear in findings (e.g., "DATABASE_URL is referenced but not in .gitignore"); their values must not.
- **Detect suspicious filenames using metadata and path inspection only.** Read file contents only when strictly necessary for analysis (e.g., dependency parsing). When content reading is needed, read the minimum required slice and discard it immediately after use.

## Repository Analysis Must Be Read-Only

- The analyser must not write, modify, delete, move, or create any file inside the repository under analysis.
- Do not create lock files, cache files, or temporary artifacts inside the target repository's directory tree.
- All temporary working files produced during analysis must be created in a system-managed temp directory outside the repository.

## Temporary Clone Lifecycle

- When a remote repository is cloned for analysis, the clone must be created in a system temp directory, never in the workspace or user home.
- The temporary clone must be deleted immediately after analysis completes — including on error paths. Use a context manager to guarantee cleanup.
- If cleanup fails, log the path as a warning so the user can remove it manually. Do not silently leave orphaned clones.

## No Transmission of Repository Contents

- The core analysis layers (`domain/`, `scanners/`, `rules/`, `scoring/`, `services/`) must not make any outbound network calls.
- Repository file contents, directory listings, and metadata must not be sent to any external service, API, or analytics endpoint.
- The `remote/` module is the only component permitted to make outbound network calls, and only to fetch the repository itself (git clone / fetch). It must not transmit any discovered file content.

## Path and URL Validation

- Validate all repository paths before use. Resolve to an absolute path and confirm the resolved path refers to a directory that exists and is readable.
- Protect against path traversal: after resolving a path inside the repository root, assert it is still a descendant of the root before reading.
- Validate remote URLs against an allowlist of supported schemes (`https://`, `git://`, `ssh://`). Reject file-scheme URLs (`file://`) and bare local paths supplied as remote URLs.
- Reject paths containing null bytes or other control characters.

## No Code Execution from Analysed Repositories

- Never `exec()`, `eval()`, `subprocess.run()`, `importlib.import_module()`, or otherwise execute code discovered in the repository being analysed.
- Do not import, load, or deserialise configuration formats in ways that allow arbitrary code execution (e.g., avoid `yaml.load()` without `Loader=yaml.SafeLoader`; avoid `pickle` for any user-supplied data).
- Build tool and test runner detection must be done by inspecting filenames and static file content — never by running the discovered tools.

## Findings Must Not Leak Sensitive Content

- Finding messages are user-visible. Before constructing a finding message, strip or redact any content that could expose credential values, private keys, or personal data.
- File contents included as evidence in a finding must be limited to non-sensitive excerpts (e.g., a dependency version string). When in doubt, omit the excerpt and reference the location only.
- Severity levels for secret-related findings must be `critical` to ensure they surface prominently.

## Dependency and Supply Chain

- Do not add dependencies that require network access at import time or that phone home during use.
- Pin or tightly bound all dependency versions to reduce supply-chain risk (see `tech.md`).
- Prefer standard library solutions over third-party packages when the functionality is comparable.

## API Layer

- The FastAPI layer must validate all user-supplied inputs (paths, URLs, options) before passing them to the service layer.
- Return generic error messages for unexpected failures; do not expose internal stack traces or filesystem paths in HTTP error responses.
- If authentication is added in the future, it must be implemented at the API layer and must never be bypassed by internal callers.
