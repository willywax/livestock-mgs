---
name: plan-feature
description: Plan a new feature or change for ShambaManager: clarify, explore affected code, write a plan, and wait for approval before editing anything.
---
# /plan-feature <feature description>
Do not edit files until the user approves the plan.
1. Clarify: restate the goal; ask only questions whose answers change the plan (roles allowed, data affected, UI needed).
2. Explore read-only: the `docs/context/codemap.md` row for the task, then the named files, `docs/DOMAIN.md`, `docs/KNOWN_ISSUES.md` (does this touch a known issue?), and matching `.claude/rules/`.
3. Write the plan: files to change (path + purpose), schema impact (additive only; if any, it needs `/db-change`), auth/roles per route, checks/tests to add (mocked, never live-HTTP), docs to update, risks, rollback, what you will NOT touch.
4. Check against: the CLAUDE.md "Never" list, stock atomicity, no Registry/outbox code, `animals.registry_tag_id` untouched.
5. End with the plan and "Approve?" and stop. After approval, implement, follow the Definition of done in CLAUDE.md, and finish with `/ship-check`.
