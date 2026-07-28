# ADR-010: Read-only code validation

## Status
Accepted

## Decision
GitHub access in v3.7 is read-only, benchmark execution is local and allow-listed, and multimodel results are emitted as reproducible JSON and Markdown artifacts.

## Consequences
PhiGraph can measure reliability without obtaining write authority over source repositories.
