---
description: Run a Design Maturity Review against Confluence design specifications.
---

Perform a design maturity review using the `design-maturity-reviewer` skill.

Please clarify your parameters if not specified in your prompt:
- **Operating Mode**: Mode A (Ticket review) or Mode B (Design baseline coverage)
- **Design Page ID**: (e.g. `123456`)
- **Jira Key**: (for Ticket mode, e.g. `PAY-123`)
- **Git Reference**: Default `origin/main`, or specify `preview` to review your uncommitted working branch

Example Prompts:
- `/dmr Review ticket PAY-123 against page 123456`
- `/dmr Preview my branch against PAY-123 and page 123456`
- `/dmr Generate coverage for design page 123456`
