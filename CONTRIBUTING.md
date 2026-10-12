# Contributing to SafetyEye

Thanks for helping improve **SafetyEye**, an AI PPE and hazard monitor for worksites (helmet/vest detection, restricted zones, fall detection, multilingual alerts) built with YOLO11 and FastAPI.

## Ways to contribute

- Report a bug or suggest an idea in [Issues](https://github.com/swapnilchaudhari007/safetyeye/issues/new/choose)
- Pick up an issue labelled `good first issue` or `help wanted`
- Improve docs, examples or translations
- Review open pull requests

## Local setup

```bash
git clone https://github.com/<your-username>/safetyeye.git
cd safetyeye
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# See README.md for running the server and web dashboard
```

## Workflow

1. Fork the repo and create a branch: `git checkout -b feat/short-description`
2. Keep each PR focused on one change
3. Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`
4. Open a PR against `main` and fill in the template

## Areas you can work on

- PPE detection (helmet / vest)
- Restricted zones
- Fall detection
- Alerts & translations
- Model training
- Web dashboard

## AI-assisted contributions

AI tools are welcome. You are responsible for every line you submit: review it, test it and say in the PR if AI helped.

## Code of conduct

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please don't report vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).
