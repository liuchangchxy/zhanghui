# Antigravity Runtime Qualification

Issue: #13  
Date: 2026-10-08

## Result

`ANTIGRAVITY_COMMON_WRITER_QUALIFIED`

Qualification applies only to the common prose-writer role used by the controlled Stage 0 comparison.

## Observed local runtime

- Desktop: Antigravity 2.21.0
- CLI/agent bridge: `~/.gemini/antigravity/bin/agentapi`
- CLI label: `hub-2.21.0`
- Auth source: Google Consumer Account OAuth via Antigravity Desktop session
- Entitlement: existing Gemini Pro / Antigravity consumer entitlement
- New Gemini API key required: no
- Incremental API billing required for the qualified writer path: no, based on the local entitlement probe

## Model identity

Observed:

- UI-selected runtime: `Gemini 3.8 Flash (Medium)`
- machine/runtime label: `MODEL_PLACEHOLDER_M322`

The exact backend model ID is not independently exposed by the machine metadata.

Therefore benchmark reports must record both labels and use:

`MODEL_ID_VERIFIABILITY = PARTIAL_INTERNAL_LABEL_ONLY`

Do not rewrite the machine label into an invented API model ID.

## Invocation qualification

Observed capabilities:

- non-interactive invocation: yes;
- fresh conversation per call: yes;
- unique conversation ID / brain directory: yes;
- prompt-file / shell-input execution: yes;
- captured output: yes;
- captured usage metadata: yes;
- cwd selection: soft only.

## Session leakage probe

Two fresh invocations were used:

- A input contained only `ALPHA-7319`;
- B input contained only `BETA-2846`.

B returned only `BETA-2846` and did not surface A's marker.

Result:

`NO_LEAKAGE_DETECTED`

This demonstrates fresh-conversation history isolation for the tested path.

## Filesystem caveat

Antigravity retains host filesystem permissions. A model could theoretically read sibling directories if given paths/tools.

Classification:

`FILESYSTEM_SOFT_ISOLATION_ONLY`

Therefore Stage 0 adds an extra controller rule:

- create a per-invocation ephemeral directory;
- serialize all writer-visible inputs into that directory;
- launch prose generation there;
- never include source/run absolute paths in the writer package;
- never instruct the writer to explore repositories/filesystem/tools;
- controller performs repository reads and ingestion outside the writer session.

## Prompt-package probe

A self-contained Chinese prose package was executed successfully through a fresh Antigravity invocation and captured as output with runtime metadata.

This validates the transport pattern:

```text
system adapter
-> serialized self-contained writer package
-> fresh Antigravity invocation
-> prose output + metadata
-> controller ingestion
```

## System transport result

### jarvis-write

Qualified: yes.

The real Composer prompt boundary can be serialized and returned prose can enter the existing precomputed/native continuation boundary.

### novel-studio

Qualified: yes, with a thin tool-call bridge.

The real sealed/primed Drafter-visible input can be serialized; prose returned by Antigravity must be wrapped into the native `draft_chapter` write boundary before the real downstream transaction continues.

### Zhanghui

Qualified: yes.

The governed Step 2A package can be serialized and returned prose can be written to the chapter draft boundary before the native review/extraction/reconciliation/ChapterCommit flow continues.

## Important scope limitation

This qualification does not prove that every system-native planner, reviewer, extractor, or maintenance model call can use the same consumer-entitlement path.

Stage 0 must separately record those calls.

If any essential system-native step requires a newly purchased API credential, stop and report it rather than silently changing the system or purchasing access.

Refs: #13
