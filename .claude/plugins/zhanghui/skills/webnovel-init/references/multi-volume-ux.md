# Multi-Volume Init UX — Design Reference

Compact rationale for the agent implementing Step 1.6 of `webnovel-init`.

## Source projects

| Project | What we borrow |
|---|---|
| `references/04-ai-agent-systems/ainovel-cli/` | Rolling planning state model: subsequent volumes may not exist; `append_volume` and `expand_arc` are explicit actions |
| `references/04-ai-agent-systems/storyforge/` | Interactive UX: AI drafts enter candidate state, user accepts/modifies/rejects; per-volume edit |
| `references/04-ai-agent-systems/tianming-novel-ai-writer/` | Per-volume field schema (most complete) |

## Three patterns we explicitly reject

| Anti-pattern | Source | Why we reject |
|---|---|---|
| Pre-fill V3-V20 empty rows | (None of the 9 references does this) | Misleads user into thinking they must fill all volumes |
| Force user to commit to total volume count | 天命 `VolumeDesignViewModel.AIGenerate.cs:207-259` | Authors often don't know up front |
| AI silently overwrites user fields | (Anti-pattern from denova `system.go:191`) | Loses user intent; AI must surface candidate state |

## The flow we implement

```
For each V_k:
  1. Ask: title / range / conflict / climax / optional fields
  2. Then offer:
     A) Continue to V_{k+1}
     B) AI draft V_{k+1} (returns CandidateVolume, user must accept)
     C) Defer ("暂不确定后续卷") — exits loop, writes confirmed_through_volume=k
     D) Bulk-paste remaining volumes
```

## Status semantics

- `confirmed`: user-confirmed, persisted to state.json
- `draft`: AI-generated, lives in memory only, user must `confirm_volume()` to persist
- `deferred`: explicit "暂不确定", persists with empty fields

## Hard constraints

- `volumes[i].index` must be contiguous (no holes) — enforced by `VolumeStateManager._check_continuity`
- AI draft cannot auto-upgrade to `confirmed` — must go through user `confirm_volume()` call
- `confirmed` fields are not overwritten by AI (defense in depth)