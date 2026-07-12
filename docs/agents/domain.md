# Domain Docs

This repository uses a single domain context.

## Before exploring

Engineering skills should read these sources when relevant:

- `CONTEXT.md` at the repository root
- ADRs under `docs/adr/`

If these files do not exist, proceed silently. Domain-modeling workflows create
them lazily when terminology or architectural decisions need to be recorded.

## Layout

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
├── backend/
└── frontend/
```

## Vocabulary

Use domain terms as defined in `CONTEXT.md`. Avoid synonyms that the glossary
explicitly rejects. If a required concept is absent, reconsider whether it is
new terminology or a genuine modeling gap.

## ADR conflicts

If proposed work contradicts an existing ADR, identify the conflict explicitly
instead of silently overriding the decision.
