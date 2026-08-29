# ADR 0001: Monorepo and service boundaries

- Status: Accepted
- Date: 2026-08-29

## Decision

Use one repository containing the web client, HTTP API, transcription worker,
shared contracts, infrastructure, and tests. Heavy model inference runs outside
the API process. The API owns validation, persistence, authorization, and task
coordination; workers own audio and model computation.

## Consequences

Contracts can be changed atomically with consumers and CI can verify the full
vertical slice. Deployment units remain independent despite sharing a repo.
