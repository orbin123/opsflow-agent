# Dataset validation report

Validated on 2026-10-04. Dataset: `data/tasks_benchmark.csv`.

## Counts and format

The final file contains **1,000 data rows plus one header row**: 1,001 physical lines. The only columns are `text,label`, in that order. Each row represents one natural-language request and exactly one allowed label.

| Label | Count |
| --- | ---: |
| `sentiment_analysis` | 125 |
| `keyword_extraction` | 125 |
| `faq_retrieval` | 125 |
| `summarization` | 125 |
| `email_drafting` | 125 |
| `reminder_creation` | 125 |
| `compound_request` | 125 |
| `out_of_scope` | 125 |
| **Total** | **1,000** |

| Validation | Result |
| --- | ---: |
| Exact duplicate texts | 0 |
| Unicode/case/punctuation-normalized duplicates | 0 |
| Confirmed near-duplicate pairs remaining after review | 0 |
| Confirmed near-duplicate clusters remaining after review | 0 |
| Malformed rows or CSV quoting errors | 0 |
| Missing or blank text | 0 |
| Missing or blank labels | 0 |
| Labels outside the allowed vocabulary | 0 |
| Extra columns or repeated headers | 0 |
| Embedded physical line breaks in text | 0 |
| Accidental Markdown, numbering, or commentary found | 0 |
| Exact label-name strings in input text | 0 |
| Examples relabeled | 0 |
| Final examples requiring unresolved label review | 0 |

The file uses UTF-8, comma delimiters, standard double-quote escaping, and LF line endings. The coordinator added the single header and shuffled the combined records deterministically with seed `20261003`; the shuffle is not a train/test split.

## Generation and review

Eight separate label batches were generated. The session allowed only three sub-agents, so the user explicitly approved reusing them:

| Sub-agent | Assigned batches |
| --- | --- |
| `sentiment_batch` | sentiment, email drafts, compound requests |
| `keywords_batch` | keywords, reminders, unsupported requests |
| `faq_batch` | FAQ retrieval, summaries |

Each batch contains exactly 125 rows and was returned as CSV data without a header. The coordinator read all examples for intent boundaries, supplied content, repetition, and accidental private information. No real personal data, contact details, credentials, or API keys were intentionally used or found. Names and operational scenarios are synthetic; general-knowledge and geography requests may reference public subjects.

Structural validation used Python's strict CSV parser plus a per-physical-line CSV grammar check. Artifact Tool preserved the combined two-column values in a round-trip check. The saved CSV was parsed again and compared with the intended records after export. No spreadsheet columns or metadata were added.

## Similarity review

All **499,500 unordered pairs** were compared across labels. Text was normalized with Unicode NFKC, case folding, and word tokenization. Screening used word TF-IDF cosine, character four-gram TF-IDF cosine, and token-set Jaccard similarity. TF used `1 + log(count)` and IDF used `1 + log((1 + N)/(1 + document_frequency))`; vectors were L2-normalized.

An initial stricter screen found no candidates. A broader screen flagged pairs when word cosine was at least **0.40**, character cosine at least **0.50**, or Jaccard at least **0.45**. It found nine candidate pairs before review. Similarity is a screening measure, not an automatic label or rejection rule. Manual comparison distinguished shared instructions from repeated substantive requests.

One pair was judged unnecessarily template-like, and one member was replaced as documented below. The other pairs were retained for these reasons:

| Shared wording or subject | Review decision |
| --- | --- |
| Five-minute calibration weight reminder / seventy-five-minute battery charger reminder | Different equipment and actions; overlap comes from reminder timing syntax. |
| Calibration weight reminder / paper-pulp consistency reminder | Different task content; overlap is the generic reminder scaffold. |
| Unused leave plus email / paid study leave plus email | Different policy questions and leave purposes; same operation pair is intentional. |
| Missing-shipment annoyance / condescending instruction | Different supplied text and emotional attitude. |
| Personal-device policy lookup / same policy topic plus separate summary | Different requested operation sets; useful FAQ-versus-compound boundary. |
| Bare sentiment question / sentiment question with training feedback | Explicitly required underspecified example versus a supplied-text example. |
| Training reimbursement lookup plus reminder / certificate email plus reminder | Different first operation and purpose despite shared training subject. |
| Replacement instead of refund email / temporary-workaround email | Different customer outcomes and email content. |

The final broader scan found **8 candidate pairs**, all reviewed as distinct requests. No confirmed near-duplicate pair or cluster remains under this review. Heuristic similarity screening and model review cannot prove the absence of every semantic paraphrase.

## Examples rejected during validation

Exactly **one** generated example was rejected for template similarity:

> Set me a nudge in thirty-five minutes to collect the washed uniforms.

It was too close in structure to the retained reminder “Need a nudge in forty-five minutes to collect the printed brochures.” The authoring sub-agent replaced it with a new request, preserving the label and batch size:

> Please queue a reminder for the morning after the exhibition closes: check that all loaned sculptures are insured for return transport.

No malformed examples were rejected, and no ambiguous example was silently repaired or relabeled. Examples requiring relabeling: **none identified**. Unresolved ambiguous examples: **none identified**.

## Boundary checks and limitations

- Summarizing an email, policy excerpt, or reminder wording remains `summarization`.
- Rewriting or composing an email, including an email about policy, remains `email_drafting` when no independent lookup or other operation is requested.
- Creating a reminder to write or summarize something later remains `reminder_creation`; performing that operation now and creating a reminder is `compound_request`.
- Separate sentiment and keyword outputs, or a policy lookup plus an email draft, are `compound_request`.
- The exact short inputs “What is the sentiment?” and “What are the key topics?” are retained in their specified classes even without a payload.
- Booking a calendar event without a reminder request, changing permissions, approving expenses, and other unsupported actions remain `out_of_scope`.

This is a synthetic classification dataset. It does not establish classifier accuracy, confidence calibration, direct-route safety, real reminder execution, or compatibility with an actual company knowledge base. Independent evaluation data and a leakage-aware split remain a separate project step; no training or model-performance test was performed.

## File fingerprint

SHA-256: `6ef925721995fc38edbee2a95cdff45a463dabc2bf0773409dab187d8f4030a0`
