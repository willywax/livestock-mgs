---
name: update-docs
description: Bring ShambaManager docs back in line with recent code changes.
---
# /update-docs
1. Find the last docs commit (`git log -1 --format=%h -- docs`), then `git log --oneline` and `git diff <that commit>..HEAD --stat`.
2. Map changes to docs: models/enums -> `docs/DATA_MODEL.md` and `docs/context/data-model.md`; routes/auth -> `docs/context/api.md`; `backend/registry_*` -> `docs/context/integration.md` (tell the user the mirrored copy in `../tags-src` needs the same edit); business rules/terms -> `docs/DOMAIN.md`; flows/modules -> `docs/ARCHITECTURE.md`; deploy/env names -> `docs/DEPLOYMENT.md`; bugs fixed or found -> `docs/KNOWN_ISSUES.md`; priorities -> `docs/ROADMAP.md`; lasting decisions -> a new `docs/decisions/NNNN-*.md`; commands/conventions -> `CLAUDE.md` (keep under 200 lines).
3. Edit only docs. Verify every path you write exists, mark inferred claims "Unverified", and include no secrets, env values or large code blocks.
4. Finish with `/update-context` and report what changed.
