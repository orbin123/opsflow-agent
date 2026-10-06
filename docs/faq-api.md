# FAQ API

`POST /api/v1/faq` is a stateless endpoint for local demo policy retrieval. It uses the shared deterministic runtime in FAQ-only mode and does not invoke the agent or maintain session history. Run the API with `.venv/bin/python -m uvicorn app.main:app` and inspect the generated contract at `/docs`.

```sh
curl -X POST http://127.0.0.1:8000/api/v1/faq \
  -H 'Content-Type: application/json' \
  -d '{"message":"What is the remote-work policy?"}'
```

Only `message` is accepted: a nonblank string up to 10,000 characters. Clients cannot supply intent or confidence. The server loads the trusted repository model, checks its SHA-256 against its metadata, and uses the saved 0.71 threshold. Model and FAQ indexes are cached; restart after changing artifacts or FAQ data.

Direct execution requires `faq_retrieval` intent at or above the threshold and one supported self-contained question. Supported extraction forms are the stored questions/alternate phrasings (ignoring case, whitespace, and trailing question punctuation), or `What is the <topic> policy?` with a short alphabetic/hyphenated topic. The latter rejects conjunctions, action words, negation, and contextual references. Either form may be wrapped in `FAQ: "…"` or curly double quotes. Other phrasing defers, even when retrieval alone could find an answer. This conservative syntax gate is not a general natural-language parser.

Response fields:

- `status`: `completed`, `agent_required`, or `error`.
- `predicted_intent`, `confidence`: the server-side classifier output; confidence is separate from FAQ similarity scores.
- `route`, `reason`: the routing decision and observable reason.
- `faq`: the existing structured retrieval result, including `matched`, `ambiguous`, or `no_match`, candidates, stored answer/policy ID when matched, and `is_demo: true`.
- `trace`: actual `retrieve_faq` execution, extracted question, result, completion/failure status, and elapsed milliseconds. Empty when the tool did not run.
- `elapsed_ms`: total endpoint execution time, including classification and any lazy initialization, excluding transport and response serialization.

Examples exercised with the saved model:

| Message | Result |
| --- | --- |
| What is the remote-work policy? | `completed`, `matched`, `REMOTE-01` |
| What is the public holidays policy? | `completed`, `ambiguous`, candidate questions without an answer |
| What is the cafeteria policy? | `completed`, `no_match` |
| Remind me tomorrow to check the remote-work policy | `agent_required`, no tool execution |

HTTP 200 means the routing attempt completed; it does not mean an answer was found or an agent ran. HTTP 422 rejects invalid bodies. HTTP 503 indicates classifier/routing unavailability (generic `detail`) or retrieval failure (`error` with a failed tool trace). Exception details are not returned.

The policies are fictional. Neither synthetic classifier evaluation nor lexical matching establishes real-world policy correctness. Unknown, compound, and context-dependent requests remain for future agent integration. This endpoint is separate from the planned session-aware `/api/v1/chat`.
