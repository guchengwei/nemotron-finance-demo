# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues at
`guchengwei/nemotron-finance-demo`. Use `gh` for operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list` with appropriate state and label filters
- Comment: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` or
  `gh issue edit <number> --remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

The repository is inferred from the current clone's Git remote.

## Pull requests as a triage surface

**PRs as a request surface: no.**

Pull requests are not included in the incoming request queue. `/triage` should
process GitHub Issues only.

## Skill operations

When a skill says to publish something to the issue tracker, create a GitHub
issue. When it says to fetch a ticket, use
`gh issue view <number> --comments`.

## Wayfinding operations

For `/wayfinder`, the map is one GitHub issue with child issues as investigation
tickets.

- Label maps with `wayfinder:map`.
- Label children with `wayfinder:<type>`.
- Prefer GitHub sub-issues and native issue dependencies.
- If those features are unavailable, use task lists and a
  `Blocked by: #<number>` line.
- Claim work by assigning the issue to the current user.
- Resolve work by recording the answer, closing the child issue, and updating
  the map's decisions.
