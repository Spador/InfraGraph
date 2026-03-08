# Execution

This folder contains deterministic Python scripts that perform the actual work — API calls, data processing, file operations, and database interactions.

## Role in the Architecture

Scripts here are **Layer 3: Execution** in the 3-layer architecture:

- **Directives** — define what to do (`directives/`)
- **Orchestration** — Claude reads directives and routes to the right scripts
- **Execution** — these scripts do the work reliably and predictably (this folder)

## Conventions

- Each script should do **one thing well** and be callable from the command line
- Accept inputs via arguments or environment variables (loaded from `.env`)
- Print clear output so the orchestration layer can parse results
- Include a comment block at the top explaining: purpose, inputs, outputs, and any dependencies
- Use `python-dotenv` to load `.env` when API keys are needed
- Handle errors explicitly — raise meaningful exceptions rather than silently failing

## Relationship to Directives

Each script is referenced by one or more directives. Before writing a new script, check whether an existing one can be reused or extended. Keep scripts general enough to be called in multiple contexts.

## Environment

- API keys and secrets live in `.env` at the project root — never hardcode them
- Install dependencies via `pip install -r requirements.txt` (create one per script or a shared one at the project root as needed)
