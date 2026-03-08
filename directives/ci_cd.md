# Directive: CI/CD Pipeline (GitHub Actions)

## Objective

Implement a GitHub Actions CI pipeline that validates every push and pull request against three quality gates: linting (Python + TypeScript), backend tests (pytest), and Docker image build. No deployment step — this is a local-only project.

---

## Inputs

| Input | Source |
|---|---|
| Python source | `backend/`, `execution/` |
| TypeScript source | `frontend/src/` |
| Test fixtures | `backend/tests/fixtures/` |
| Docker build contexts | `backend/Dockerfile`, `frontend/Dockerfile` |
| Trigger conditions | Push to `main` or `develop`; PR targeting `main` |

---

## Tools / Scripts

- **Reference pipeline**: `.claude/skills/devops-iac-engineer/examples/pipelines/github-actions.yml`
- **Python lint**: `flake8` (config in `backend/setup.cfg` or inline `--max-line-length=120`)
- **JS lint**: `eslint` with TypeScript plugin
- **TS type check**: `tsc --noEmit`
- **Tests**: `pytest` with `-v --tb=short`
- **Build**: `docker compose build`

---

## Outputs

| Job | Success Condition |
|---|---|
| `lint` | `flake8` exits 0; `eslint` exits 0; `tsc --noEmit` exits 0 |
| `test` | All pytest tests pass (exit 0) |
| `build` | All Docker images build without error |

---

## Pipeline Structure

**Triggers**:
```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
```

**Job ordering**:
```
lint  ──┬──► test   (parallel after lint)
        └──► build  (parallel after lint)
```

---

## Job Definitions

### Job: lint

```yaml
lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    # Python lint
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install flake8
      run: pip install flake8
    - name: Lint Python
      run: flake8 backend/ execution/ --max-line-length=120 --exclude=__pycache__,*.pyc,.venv,venv

    # TypeScript / JS lint
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
        cache: 'npm'
        cache-dependency-path: frontend/package-lock.json
    - name: Install frontend dependencies
      run: cd frontend && npm ci
    - name: ESLint
      run: cd frontend && npx eslint src/ --ext .ts,.tsx --max-warnings=0
    - name: TypeScript type check
      run: cd frontend && npx tsc --noEmit
```

### Job: test

```yaml
test:
  needs: lint
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install backend dependencies
      run: pip install -r backend/requirements.txt
    - name: Run tests
      run: pytest backend/tests/ -v --tb=short
```

**Notes**:
- Tests must not require a live Neo4j instance — parser tests are pure Python
- If Neo4j integration tests are added later, use `testcontainers-neo4j` (see `neo4j-docker-client-generator.md`)

### Job: build

```yaml
build:
  needs: lint
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    - name: Build images
      run: docker compose build
```

**Notes**:
- `docker compose build` only — does NOT run the stack (no `docker compose up`)
- This validates that all Dockerfiles are syntactically correct and all dependencies install cleanly
- No images are pushed to any registry

---

## ESLint Configuration

`frontend/.eslintrc.json`:
```json
{
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended"
  ],
  "parser": "@typescript-eslint/parser",
  "plugins": ["@typescript-eslint"],
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "no-console": "warn"
  },
  "env": { "browser": true, "es2022": true }
}
```

Install in `frontend/package.json` dev dependencies:
- `eslint`
- `@typescript-eslint/eslint-plugin`
- `@typescript-eslint/parser`
- `eslint-plugin-react-hooks`

---

## flake8 Configuration

`backend/setup.cfg`:
```ini
[flake8]
max-line-length = 120
exclude = __pycache__, *.pyc, .venv, venv, .tmp
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| `npm ci` fails (no `package-lock.json`) | Commit `package-lock.json`; `npm ci` requires it |
| `flake8` finds issues | Fix before merging; CI blocks PRs |
| Pytest import errors (missing deps) | All deps in `backend/requirements.txt`; CI installs them |
| Docker build fails due to base image pull | Transient network issue; re-run CI job |
| `tsc --noEmit` finds type errors | Fix before merging; CI blocks PRs |
| New test file added | Automatically picked up by `pytest backend/tests/` |
| `.env` not committed | `docker compose build` uses `docker-compose.yml` defaults; no `.env` needed for build step |

---

## Future Additions (not in MVP)

- `docker compose up` integration test against a live Neo4j in CI (using service containers)
- Code coverage reporting (`pytest --cov=backend/app`)
- Security scanning (`bandit` for Python, `npm audit` for Node)
- Dependabot for dependency updates

---

## Update Log

- Initial version: lint → (test + build) parallel, Python + TypeScript lint, pytest, docker compose build
- flake8 issues found and fixed before CI was written:
  - `test_terraform_parser.py`: `import tempfile` unused (removed)
  - `neo4j_load.py`: `from pathlib import Path` unused (removed)
  - `parse_terraform.py`: `known_ids` assigned but never used (removed)
  - `seed_loader.py`: E302 missing blank line before function def (added)
- `backend/setup.cfg` created with `[flake8]` section so flake8 picks up config automatically
- `npm ci` requires `frontend/package-lock.json` to be committed — it is present from `npm install` run during M6
