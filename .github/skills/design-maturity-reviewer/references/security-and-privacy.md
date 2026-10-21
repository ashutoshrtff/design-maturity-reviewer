# Security, Privacy & Subprocess Safety

## Secret Handling
- **No Hardcoded Tokens**: Tokens are read solely from environment variables (`ATLASSIAN_API_TOKEN`, `ATLASSIAN_PAT`, `OPENAI_API_KEY`).
- **No Secret Logging**: Credentials and authorization headers are never printed to console, reports, or logs.
- **Enterprise Hostnames**: Fully supports custom GitHub Enterprise Server (GHES) and Data Residency hostnames (`*.ghe.com`).

## Subprocess Execution
- All Git and CLI invocations use safe list arguments (`subprocess.run(['git', ...])`).
- No shell interpolation (`shell=True` is prohibited).
- Path traversal outside repository root is blocked.

## Prompt Injection Defense
- Content retrieved from Jira tickets and Confluence pages is treated strictly as passive data, never executed as agent instructions.
