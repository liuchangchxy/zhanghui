---
name: webnovel-correction-confirm
description: Review and record a human decision for one staged Canon correction request. Use only when a correction request already exists and a user explicitly asks to review it.
allowed-tools: Read, Bash, AskUserQuestion
---

# Review a staged Canon correction

This workflow records a decision on one immutable correction request. It does not activate the correction.

1. Read the request's current effective parent state from the effective history workflow. Do not infer the parent from a sibling proposal or choose among conflicting candidates.
2. Run `webnovel.py --project-root <fixture-or-book-root> correction review-package --request-id <id> --parent-state-file <state.json>`. The command validates the request and parent content digest, then prints the canonical review package.
3. Show the complete package to the user, including request and base digests, parent revision and content digest, operation, changed paths, reason, and before/after semantic content. Ask the user with the host's direct interactive question UI to choose `APPROVE` or `REJECT`. Do not select a choice, infer one from chat context, or continue if the user gives no answer or the UI is unavailable.
4. Only after the user answers, save the exact displayed package to a temporary JSON file and run `webnovel.py --project-root <fixture-or-book-root> correction record-decision --request-id <id> --review-package-file <package.json> --choice <user-choice>`.
5. Report the resulting authorization ID and digest. Keep rejected requests terminal. Any changed request, parent, or semantic content requires a new request ID and a fresh review.

The authorization is persisted only through the existing `CanonCorrectionAuthorization` v1 store. Python checks exact request and challenge bindings but does not authenticate who answered or prove the UI origin. Never describe this record as cryptographic identity evidence.

No answer or an unavailable interaction UI leaves the request pending and creates no authorization. A correction remains staged after approval; activation is a separate operation.
