# Agent Change Record

Keep entries brief: date, completed change, verification, and any changed decision. Track actual work rather than restating the plan.

- **2026-10-03:** Added `docs/PLAN.md`, `docs/agents_doc.md`, and root `AGENTS.md`. Confirmed v1 emails the user with separate draft/instructions sections; reminders always use agent orchestration and include due-time email delivery. Direct sentiment receives the extracted text. Reviewed documents for consistency with the agreed scope; no application code or runtime tests yet.
- **2026-10-03:** Changed the planned classifier dataset from JSON to CSV with `text,label` columns. Increased the initial synthetic benchmark target from 120 to 1,000 rows, to be generated and reviewed in coordinated batches. The classifier will train on text and labels only; route/tool metadata remains outside the first training CSV.

- **2026-10-03:** Defined all eight dataset labels and generated the first three 125-row batches. The user approved reusing three sub-agents for the remaining batches after the session refused a fourth agent.
- **2026-10-04:** Completed `data/tasks_benchmark.csv` with exactly 1,000 examples, 125 per label, and only `text,label`. Strict CSV/shape/count/blank/label checks and value round-trip checks passed. Reviewed all examples and all 499,500 pairs through similarity screening; replaced one template-like reminder and logged it in `docs/dataset_validation_report.md`. No exact/normalized duplicates, confirmed near-duplicate clusters, or unresolved relabeling cases were identified. No classifier training or independent evaluation split performed.

**Next:** Review the final dataset/report with the user and agree on company FAQ grounding and the independent evaluation split before training the router.
