# Contributing

## Workflow

1. Create a short-lived branch from `main`: `feat/...`, `fix/...`, or `chore/...`.
2. Keep commits focused and use Conventional Commits.
3. Run the relevant formatters, type checks, tests, and builds before opening a PR.
4. Update contracts, tests, and documentation with behavior changes.

Never commit user audio, generated stems, model weights, credentials, databases,
or build artifacts. New model integrations require a license review in
`docs/model-licenses.md`.

## Commit examples

- `feat(api): add transcription job endpoint`
- `fix(score): preserve source timing during requantization`
- `chore(repo): initialize monorepo tooling`
