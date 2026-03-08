# Directives

This folder contains SOPs (Standard Operating Procedures) written in Markdown. Each file defines a discrete task the orchestration layer (Claude) can execute.

## Role in the Architecture

Directives are **Layer 1: Directive** in the 3-layer architecture:

- **Directives** — define *what* to do (this folder)
- **Orchestration** — Claude reads directives and decides *how* to route execution
- **Execution** — deterministic Python scripts in `execution/` do the actual work

## What a Directive Contains

Each `.md` file should include:

- **Objective** — what the task accomplishes
- **Inputs** — what data or parameters are required
- **Tools/Scripts** — which `execution/` scripts to call and in what order
- **Outputs** — what is produced (files, API responses, cloud deliverables)
- **Edge Cases** — known failure modes, rate limits, or special handling

## How to Write a Directive

Write it as you would instruct a capable mid-level employee. Be specific enough that the task can be executed without ambiguity, but don't hard-code values that belong in `.env` or script arguments.

## How to Update a Directive

Directives are living documents. Update them when you discover:

- API constraints or rate limits
- Better approaches or script changes
- Common errors and how to handle them
- New edge cases

Do not discard directives after use — improve them so the system gets stronger over time.
