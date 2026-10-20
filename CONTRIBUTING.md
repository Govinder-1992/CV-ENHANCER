# Contributing to CV Enhancer

Thanks for your interest in contributing. This guide covers how to set up,
change, and submit improvements to the project.

## Project structure

See the [Repository layout](README.md#repository-layout) in the README. In
short:

- **Frontend** — `index.html`, `styles.css`, `app.js`, `config.js` (static site).
- **Backend** — `src/app` (worker Lambda) and `src/common` (shared utilities).
- **Infrastructure** — `template.yaml` (AWS SAM).
- **CI/CD** — `.github/workflows/deploy.yml`.
- **Diagram** — `diagram/architecture.py`.

## Prerequisites

- AWS SAM CLI, AWS CLI (configured), Python 3.12.
- For the diagram: Graphviz + `pip install diagrams`.

## Local development

### Frontend

```powershell
python -m http.server 8080   # then open http://localhost:8080
```

Set `API_ENDPOINT` in `config.js` to a deployed API, or test against a sandbox
stack.

### Backend

```powershell
sam build
sam validate --lint
```

Compile-check the Python before pushing:

```powershell
python -m py_compile (Get-ChildItem -Recurse src -Filter *.py | ForEach-Object FullName)
```

## Branching & commits

- Create a feature branch off `main`: `git checkout -b feature/short-name`.
- Write clear, imperative commit messages (e.g. "Add X", "Fix Y").
- Keep each PR focused on a single concern.

## Pull requests

1. Ensure `sam validate --lint` passes and the Python compiles.
2. If you changed the architecture, regenerate the diagram:
   ```powershell
   cd diagram
   python architecture.py
   ```
3. Update the README if behavior, parameters, or endpoints changed.
4. Open a PR against `main` describing **what** changed and **why**, and note
   anything you could not test.

## CI/CD

Pushing to `main` triggers `.github/workflows/deploy.yml`, which deploys the
backend and publishes the frontend. PRs do **not** deploy — only merges to
`main` do. Required repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Coding conventions

- **Python**: follow the existing style — typed errors in `common/errors.py`,
  structured logging via `common/logging_utils.py`, and keep the worker's
  error handling (transient vs permanent) intact.
- **Security**: never store the original CV; keep IAM least-privilege; don't put
  secrets in code or commits.
- **Frontend**: vanilla JS, no build step. Keep validation client-side first.

## Reporting issues

Open a GitHub issue with steps to reproduce, expected vs actual behavior, and
relevant logs (scrub any personal data). For security concerns, avoid posting
sensitive details publicly.
