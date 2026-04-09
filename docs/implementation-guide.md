# Implementation Guide: Phase 1 Security Remediation & Tests

TL;DR
- **What:** Concrete, repeatable steps to apply Phase‑1 (P0) security fixes: remove hard-coded credentials, secure temporary/artifact files, limit XCom usage, add pinned dependency manifests, and run initial checks.
- **Scope:** Phase‑1 only — docker-compose, three DAGs, requirements files, and developer guidance. Phase‑2 (config validation, import safety) and Phase‑3 (tests) are described as next steps.
- **Assumptions:** You will run the changes locally (Windows or POSIX). No external secret manager is configured. This guide documents edits and verification steps and includes commands to create the file.

## Overview
- **Goal:** Reduce immediate attack surface: eliminate hard-coded secrets, prevent predictable temp file attacks, and stop large/sensitive objects from being stored in Airflow XCom.
- **Branching:** Work in a short-lived feature branch named `fix/security/p0-credentials-tempfiles` (or `fix/security/p0-credentials-tempfiles-1` if the former exists).
- **Acceptance:** After applying changes, all modified DAGs import cleanly and syntax checks pass, no sensitive defaults remain in docker-compose, artifact files are written to a controlled directory with secure permissions, and `requirements.txt`/`requirements-dev.txt` exist.

## Files touched in Phase 1
- `docker-compose.yaml` — remove hard-coded secrets; reference env vars
- `requirements.txt` — pinned runtime deps
- `requirements-dev.txt` — dev tools (bandit, pytest, pip-audit, etc.)
- `dags/drift_monitoring.py` — use `ARTIFACT_DIR` + UUID artifacts; push URIs to XCom
- `dags/inference_ingestion.py` — same: artifact dir, tmp artifact URIs
- `dags/retraining_trigger.py` — same: dataset artifacts, secure model registry writes

## Exact `.env.template` (create at repo root)
Use this template (do NOT commit real secrets; put them in `.env` which must be gitignored).

```
POSTGRES_PASSWORD=REPLACE_ME
_AIRFLOW_WWW_USER_PASSWORD=REPLACE_ME
REDIS_PASSWORD=REPLACE_ME
SLACK_WEBHOOK_URL=REPLACE_ME
AIRFLOW__CORE__FERNET_KEY=REPLACE_ME
ARTIFACT_DIR=/opt/airflow/data/artifacts
```

## High-level change summary
- `docker-compose.yaml`: replace cleartext defaults with `${VAR}` interpolation and add `env_file: - .env` usage in service definitions (example listed below).
- DAGs: replace `/tmp` usage with `ARTIFACT_DIR` (defaults to `/opt/airflow/data/artifacts`), create directory with `0o700` perms, write artifact files with non-predictable names (UUID or secure hex), set files to `0o600`, and push only artifact URIs via XCom.
- Add `requirements.txt` and `requirements-dev.txt` (pinned).
- Do not change XCom encryption in Phase 1 — document that for Phase 2.

## Concrete edits (illustrative snippets)

- `docker-compose.yaml` — replace these lines
  - From:
    - `POSTGRES_PASSWORD: airflow`
    - `AIRFLOW__CORE__FERNET_KEY: ""`
    - `SLACK_WEBHOOK_URL: ""`
    - `_AIRFLOW_WWW_USER_PASSWORD: ${_AIRFLOW_WWW_USER_PASSWORD:-airflow}`
    - `AIRFLOW__CELERY__BROKER_URL: redis://:@redis:6379/0`
  - To:
    - `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`
    - `AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW__CORE__FERNET_KEY}`
    - `SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}`
    - `_AIRFLOW_WWW_USER_PASSWORD: ${_AIRFLOW_WWW_USER_PASSWORD}`
    - `AIRFLOW__CELERY__BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/0`
  - Note: Add `env_file: - .env` where appropriate for services.

- DAG artifact pattern (pseudo-change example)
  - Before (unsafe predictable tmp):
    - `/tmp/ml_drift/tmp_baseline.parquet`
  - After (safe):
    - `ARTIFACT_DIR = Path(os.environ.get('ARTIFACT_DIR', '/opt/airflow/data/artifacts'))`
    - `ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)` (attempt to set `0o700`)
    - `artifact = ARTIFACT_DIR / f"baseline_{uuid4().hex}.parquet"`
    - `df.to_parquet(artifact, index=False)`
    - `os.chmod(artifact, 0o600)` (best effort)
    - `ti.xcom_push(key='baseline_artifact_uri', value=str(artifact))`
  - When reading:
    - `uri = ti.xcom_pull(key='baseline_artifact_uri', task_ids='load_baseline')`
    - `p = Path(uri).resolve()`
    - Validate `p` is inside `ARTIFACT_DIR` (prevent traversal) before opening.

## How to apply Phase‑1 locally (recommended, one-shot script)
- Option A — run the automation script provided earlier `scripts/apply_p0_security_changes.py`.

POSIX / WSL / Git Bash:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/apply_p0_security_changes.py
```

PowerShell (Windows):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python .\scripts\apply_p0_security_changes.py
```

- Option B — Manual steps (if you prefer manual edit):
  1. Create and checkout branch:
     - `git checkout -b fix/security/p0-credentials-tempfiles`
  2. Create `.env.template` and ensure `.env` is in `.gitignore`.
  3. Edit `docker-compose.yaml` per the replacements shown.
  4. Create `requirements.txt` and `requirements-dev.txt` with pinned versions.
  5. Modify the three DAGs per the artifact pattern snippet above (replace tmp writes, change XCom keys, set perms).
  6. Stage and commit with focused messages:
     - `git add .env.template docker-compose.yaml && git commit -m "chore(secrets): move sensitive defaults to .env variables"`
     - `git add requirements*.txt && git commit -m "chore(deps): add pinned requirements and dev requirements"`
     - per-DAG commits: `fix(dag): secure artifact handling in <filename>`

## Verification — run these checks after changes
- Syntax / byte-compile:
```bash
python -m compileall .
```
- Static security scan (bandit):
```bash
bandit -r dags/ src/ -ll
```
- Dependency audit:
```bash
pip-audit --progress-spinner off
# and
safety check
```
- Quick unit tests (once tests added):
```bash
pytest tests/ -v --maxfail=1 --disable-warnings
pytest --cov=src --cov-report=html
```
- DAG sanity (without full Airflow infra): import-check DAG modules
```bash
python -c "import importlib; importlib.import_module('dags.drift_monitoring')"
```
- Review docker-compose:
  - Check that `docker-compose.yaml` references `${...}` and no longer contains plaintext passwords.

## Review checklist before merge
- **Secrets:** No hard-coded credentials remain in `docker-compose.yaml`. `.env.template` exists. `.env` is gitignored.
- **Artifact handling:** All DAGs write artifacts under `ARTIFACT_DIR`, filenames are non-predictable (UUID/hex), directories created with owner-only perms where possible, files chmod’d to `0o600` where possible.
- **XCom hygiene:** No DataFrames or large objects serialized into XCom; only URIs or minimal metadata.
- **Deps:** `requirements.txt` and `requirements-dev.txt` present and pinned.
- **Checks:** `python -m compileall .` succeeds; bandit and pip-audit produce no blocking findings (or issues are triaged).
- **Commits:** Small, focused commits with clear messages and rationale.

## Rollout & secrets
- **Local dev:** Create a local `.env` from `.env.template` and secure it:
```bash
cp .env.template .env
# Edit .env to insert generated secrets.
# Restrict permissions:
chmod 600 .env
```
- **Secret generation:** Use a secure generator:
```bash
python - <<'PY'
import secrets, base64
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
```
- **Production:** Use a secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager) or Docker secrets — do NOT store production secrets in Git.

## Rollback
- If a change breaks DAG imports or Airflow run, revert the branch or reset the affected files:
```bash
git checkout main
git revert <merge-commit-sha>
```

## Next steps (Phase 2 / 3 recommended)
- **Phase 2 (P1):**
  - Implement pydantic validation in `src/drift/thresholds.py`.
  - Validate environment variables and allowed paths.
  - Replace `sys.path.insert` import patterns with proper package imports or `importlib`.
  - Harden alert modules (specific exception handling).
  - Consider enabling/encrypting XCom (Fernet) or implement an encrypted XCom backend.
- **Phase 3 (Tests):**
  - Add unit tests for psi/ks/validators/loaders and lightweight DAG integration tests (mocks for file IO & ti).
  - Add CI workflow template (GitHub Actions) to run bandit, pip-audit, and pytest on PRs.
- **Operational:**
  - Add pre-commit hooks: bandit, detect-secrets.
  - Plan secret rotation and audit schedule (bandit, pip-audit monthly).

## Contacts & maintainers notes
- Add a short note to README describing that `.env.template` exists, `.env` must not be committed, and where to find the implementation guide.

---

This file documents Phase‑1 remediation steps and commands; apply changes and run the checks listed above. For Phase‑2/3 I can proceed after Phase‑1 verification.
