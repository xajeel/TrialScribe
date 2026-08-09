# TrialScribe

AI-powered clinical research assistant for drafting citation-backed ICH M11 clinical trial
protocol sections. Project context, commands, and the code rulebook live in `.sdlc/` —
read `.sdlc/PROJECT.md` and `.sdlc/CRAFT.md` before changing code.

## Git workflow — always applies

These rules come from `.claude/rules/git-workflow.md` and are restated here because that file
is not loaded automatically.

1. **Never make a change directly on `main`.**
2. **Branch every feature off `staging`.** If `staging` does not exist, create it from `main` first.
3. **Name feature branches `xajeel-<feature-name>`** — e.g. `xajeel-auth-fix`,
   `xajeel-kafka-event-backbone`. Do not use `feat/<feature>`, even when a skill suggests it.
4. **Feature branch → pull request into `staging`.** Never commit straight to `staging`.
5. **Release by merging `staging` into `main` manually.**
6. **Never push unless asked.** Commit locally and report the push command.

## Commits

- Conventional Commits: `<type>(<feature>): <subject>`, subject ≤ 72 characters.
- Do **not** add a `Co-Authored-By: Claude` trailer, or any AI co-author trailer.

## SDLC

Feature work runs through the skills in `.claude/skills/` — `/spec`, `/build`, `/qa`, `/ship`,
or `/automate <feature>` for the whole cycle. State lives in `.sdlc/STATE.md`, the feature list
in `.sdlc/ROADMAP.md`, and past defects in `.sdlc/BUGS.md`. `.sdlc/` is gitignored, so its
updates never appear in a commit.

Specs are written for people: the **Mental model** and **Decisions** sections must be readable by
someone with no coding background. Define any technical term in plain words at first use.
