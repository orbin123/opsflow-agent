# OpsFlow-Agent walkthrough

Recorded 15 October 2026 from main at `3ed5232`. Duration: 00:05:47.

Actual 1440 × 900 browser capture of the local Streamlit application, with live
Groq responses and synthetic narration (macOS Daniel voice). English captions are
selectable in the MP4; the WebVTT sidecar is also included. Two capture segments
are joined, removing initial loading and a navigation-automation pause. Task
execution footage runs at normal speed; responses are actual application output.

## Chapters

- **00:00:00** — What OpsFlow-Agent does
- **00:00:21** — Example 1 — fictional policy lookup
- **00:01:31** — Example 2 — analysis, keywords, summary and draft
- **00:03:17** — Example 3 — reminder scheduling
- **00:04:06** — Saved reminders and delivery states
- **00:04:25** — Saved email drafts
- **00:04:47** — Classifier evaluation
- **00:05:06** — Generation review
- **00:05:27** — Refresh and saved restoration

## Demonstrated behavior

1. A remote-work policy request executes `retrieve_faq` through the fixed FAQ workflow.
2. A complaint request uses `analyze_sentiment`, `extract_keywords`, `summarize_text` and `draft_email`.
3. A one-time reminder request uses `schedule_reminder` and appears as scheduled in Settings.
4. Settings reads saved reminders, drafts and evaluation evidence. Refresh restores the saved chat.

All three requests completed in the recorded run. Check the application’s saved Activity for exact outputs; this is representative demonstration evidence, not a general model-quality benchmark. The FAQ is fictional; the draft was not sent. The reminder is in a separate demonstration database and the delivery worker was never started. Normal local chat/reminder databases were not used.

## Files

- [Narrated MP4](opsflow-walkthrough.mp4)
- [English WebVTT captions](opsflow-walkthrough.vtt)
- [Project README](../README.md)
