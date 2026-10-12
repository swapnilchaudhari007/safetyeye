# Security Policy

## Supported versions

Only the latest code on `main` is supported.

## Reporting a vulnerability

**Please don't open a public issue.** Use the repo's **Security** tab → **Report a vulnerability**, or contact [@swapnilchaudhari007](https://github.com/swapnilchaudhari007).

Include a description, the impact, steps to reproduce and any suggested fix. You'll get an acknowledgement within 72 hours and an initial assessment within 7 days. Reporters are credited unless they'd rather stay anonymous.

## What we especially care about in SafetyEye

- **Missed detections:** inputs or conditions that make the model silently miss a person without PPE or a fall
- **Camera privacy:** video frames or faces stored or sent anywhere without consent
- **Model tampering:** loading untrusted model weights (pickle-based files can run code)
- **Unauthenticated dashboard or API access** on a worksite network

## For contributors

- Never commit secrets: use `.env` files (git-ignored) or GitHub Actions secrets
- Keep real personal data out of code, tests, issues and screenshots
- Treat all user input, and anything passed to an AI model, as untrusted
