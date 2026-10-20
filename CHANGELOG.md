# Changelog

## 0.6.32 — 2026-10-20

- Reduced minimum workspace dimensions and made both panes shrinkable to avoid GTK negative-size allocations on smaller or scaled displays.
- Adaptive divider sizing now preserves nonzero space for both PCB canvas and context pane when the window is narrow.

## 0.6.31 — 2026-10-20

- Follow-up audit release: persisted user preferences and chats, introduced the multiline composer, tightened KiCad S-expression validation, and documented actual support boundaries.
- Made `VERSION` the single source of truth for runtime, Python metadata and Debian packaging.

## 0.6.30 — 2026-10-20

- Added local SQLite storage and retrieval for component troubleshooting cases; model-generated cases remain marked unverified.
- Added persistence for AI/user chat messages; no transient status/system messages are archived as chat.
- Added persistent, permission-protected user settings for application display name and Ollama model/endpoint.
- Replaced the one-line AI question field with a multiline GTK text composer; Enter sends and Shift+Enter inserts a newline; failed question text is retained for retry.
- Rejected trailing data after a top-level KiCad board S-expression.

## 0.6.29

- Strengthened safe-voltage guidance and response handling for model output.

## 0.6.28

- Kept the PCB canvas and AI pane within divider bounds and scaled component labels with readable limits.
