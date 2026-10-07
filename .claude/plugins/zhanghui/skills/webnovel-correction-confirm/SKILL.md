---
name: webnovel-correction-confirm
description: Review, confirm, and activate one staged Canon correction. Use only when a correction request already exists and the user explicitly asks to review it.
allowed-tools: Read, Bash, AskUserQuestion
---

# Review a staged Canon correction

This workflow reviews one immutable correction request. Make clear that `APPROVE` authorizes activation of the exact displayed correction into active Canon after validation; `REJECT` leaves active Canon unchanged.

1. Read the request's current effective parent state from the effective history workflow. Do not infer the parent from a sibling proposal or choose among conflicting candidates.
2. Run `webnovel.py --project-root <fixture-or-book-root> correction review-package --request-id <id> --parent-state-file <state.json>`. The command validates the request and parent content digest, then prints the canonical review package.
3. Show the complete package to the user, including request and base digests, parent revision and content digest, operation, changed paths, reason, and before/after semantic content. State that approval will activate this exact content if validation succeeds. Ask the user with the host's direct interactive question UI to choose `APPROVE` or `REJECT`. Do not select a choice, infer one from chat context, or continue if the user gives no answer or the UI is unavailable.
4. Only after the user answers, save the exact displayed package to a temporary JSON file and run `webnovel.py --project-root <fixture-or-book-root> correction record-decision --request-id <id> --review-package-file <package.json> --choice <user-choice>`. Save the returned authorization JSON unchanged to a temporary file.
5. If the answer is `APPROVE`, run `webnovel.py --project-root <fixture-or-book-root> correction activate --correction-id <correction-id> --authorization-file <authorization.json>`. This builds and validates a complete Canon generation, then publishes it atomically. If activation fails, report the active publication remains unchanged unless the command reports an already-published idempotent result; the saved authorization may be retried only after reviewing the current candidate status. A `REJECT` answer never invokes activation.
6. Report the resulting authorization ID/digest and activation publication ID/effective revision. Keep rejected requests terminal. Any changed request, parent, or semantic content requires a new request ID and a fresh review.

The authorization is persisted only through the existing `CanonCorrectionAuthorization` v1 store. Python checks exact request and challenge bindings but does not authenticate who answered or prove the UI origin. Never describe this record as cryptographic identity evidence.

No answer or an unavailable interaction UI leaves the request pending and creates no authorization. Staging alone never changes active history. The approved workflow activates only after the existing authorization has been persisted and all request, authorization, lineage, and generation checks pass.
