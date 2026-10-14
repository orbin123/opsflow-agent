"""Two readable evaluation sections; opening the page never executes work."""

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from app.evaluation.classifier_report import ClassifierReport
from app.evaluation.generation_quality import GenerationReview
from app.ui.ui_client import ChatClientError

INTENTS = {
    "compound_request": "Compound requests",
    "email_drafting": "Email drafting",
    "faq_retrieval": "FAQ retrieval",
    "keyword_extraction": "Keyword extraction",
    "out_of_scope": "Out of scope",
    "reminder_creation": "Reminder creation",
    "sentiment_analysis": "Sentiment analysis",
    "summarization": "Summarization",
}
CRITERIA = (
    ("Faithfulness", "Facts are supported by the source.",
     "Compare each factual claim with the supplied text, retrieved policy or actual tool result. "
     "Invented numbers, dates, policies or promises reduce the rating."),
    ("Coverage", "Required facts and uncertainty are included.",
     "Check whether the answer includes each fact required to answer the request, preserving "
     "qualifiers and uncertainty. An accurate answer can still omit required information."),
    ("Relevance", "The answer addresses the request.",
     "Compare the answer with the user's question. Check that it addresses the main request "
     "and avoids distracting or unrelated additions."),
    ("Instruction compliance", "Requested format, tone and constraints are followed.",
     "Check the requested format, tone and explicit constraints. Commands embedded in source "
     "text must be treated as data rather than followed as instructions."),
    ("Status accuracy", "Completed, failed and scheduled work is described correctly.",
     "Compare action claims with actual execution and storage outcomes. A draft is not sent; "
     "a scheduled reminder is not delivered. Unfinished work must remain explicit."),
    ("Context relevance", "The right source or conversation context is used.",
     "Check whether the supplied source, retrieved policy or prior conversation is relevant "
     "to the current request, and whether missing information is acknowledged."),
)


def get_classifier_report(base_url: str) -> ClassifierReport:
    request = Request(base_url.rstrip("/") + "/api/v1/evaluations", method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise ChatClientError("Classifier results are unavailable.")
            return ClassifierReport.model_validate_json(response.read())
    except (HTTPError, URLError, OSError, ValueError):
        raise ChatClientError("Classifier results are unavailable.") from None


def classification_rows(report: ClassifierReport) -> list[dict]:
    rows = [{"Intent": INTENTS[label], "Precision": f"{scores.precision:.4f}",
             "Recall": f"{scores.recall:.4f}", "F1 score": f"{scores.f1:.4f}",
             "Support": int(scores.support)}
            for label in report.dataset.labels for scores in [report.test_metrics.per_label[label]]]
    for name, averages in zip(("Macro average", "Weighted average"), report.averages()):
        rows.append({"Intent": name, "Precision": f"{averages['Precision']:.4f}",
                     "Recall": f"{averages['Recall']:.4f}", "F1 score": f"{averages['F1']:.4f}",
                     "Support": report.split.test_rows})
    return rows


def get_generation_review(base_url: str) -> GenerationReview:
    request = Request(base_url.rstrip("/") + "/api/v1/evaluations/generation", method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise ChatClientError("Generation review is unavailable.")
            return GenerationReview.model_validate_json(response.read())
    except (HTTPError, URLError, OSError, ValueError):
        raise ChatClientError("Generation review is unavailable.") from None


def generation_rows(review: GenerationReview | None) -> list[dict]:
    scores = review.dimension_scores() if review else {}
    rows = []
    for name, _, _ in CRITERIA:
        result = scores.get(name.lower().replace(" ", "_"))
        rows.append({"Dimension": name,
                     "AI rating (0–3)": f"{result['mean']:.2f}" if result and result["mean"] is not None else "Not scored",
                     "Reviewed answers": f"{result['scored']} / {result['applicable']}" if result else "Unavailable"})
    return rows


def show_evaluations(base_url: str) -> None:
    st.header("Evaluations")
    st.subheader("Classifier report")
    st.caption("Word TF-IDF + a calibrated linear SVM classifies requests into eight intents.")
    try:
        report = get_classifier_report(base_url)
    except ChatClientError as exc:
        report = None
        st.error(str(exc))
    if report is not None:
        st.metric("Holdout accuracy", f"{report.test_metrics.accuracy:.1%}")
        st.table(classification_rows(report), hide_index=True,
                 alt="Classifier precision, recall, F1 and support for all eight intents and averages")
        st.caption("Precision, recall and F1 range from 0 to 1; higher is better. Support is the number of test examples.")
    with st.expander("How classifier results are calculated"):
        if report is not None:
            st.markdown(
                f"**Data:** {report.dataset.row_count:,} fictional labelled requests from `data/tasks_benchmark.csv`. "
                f"A stratified split used {report.split.development_rows:,} development examples and "
                f"{report.split.test_rows:,} holdout examples. Each intent's support is shown above.\n\n"
                f"**Source:** Results recorded alongside the trained model on {report.created_on.strftime('%d %B %Y')} "
                "in `artifacts/models/intent_router_svm_metadata.json`. This page reads those results; "
                "it does not rerun or retrain the classifier. They describe the recorded synthetic holdout, "
                "not current live chat or generated-answer quality."
            )
        else:
            st.markdown("The page requires valid results saved alongside the trained classifier. "
                        "Missing or mismatched results are unavailable, never a zero score or a pass.")
        st.markdown(
            "**Accuracy:** Correct intent predictions ÷ all test examples.\n\n"
            "**Precision:** Correct predictions of an intent ÷ all predictions of that intent.\n\n"
            "**Recall:** Correct predictions of an intent ÷ all examples labelled with that intent.\n\n"
            "**F1:** 2 × precision × recall ÷ (precision + recall). The recorded scorer uses zero "
            "when the denominator is zero.\n\n"
            "**Weighting:** Macro averages give each of the eight intents equal weight (12.5% each). "
            "Weighted averages use each intent's share of test examples. The two averages coincide "
            "when every intent has equal support. No additional custom weights are applied."
        )
    st.subheader("Generation quality")
    try:
        review = get_generation_review(base_url)
    except ChatClientError as exc:
        review = None
        st.error(str(exc))
    if review:
        available = sum(bool(c.answer and c.answer.strip()) for c in review.cases)
        st.caption(f"AI subagent review · {available} of {len(review.cases)} planned answers available. "
                   "Scores describe this fictional development sample; human review is pending.")
        findings = [finding for case in review.cases for finding in case.critical_findings]
        if findings:
            st.warning(f"The review identified {len(findings)} critical finding(s). See the explanation below.")
    st.table(generation_rows(review), hide_index=True,
             alt="AI-reviewed generation quality ratings and reviewed versus applicable answer counts")
    with st.expander("How generation quality is assessed"):
        st.markdown(
            "**Method:** An AI subagent assesses actual application answers against each request, source "
            "text, retrieved policy, relevant history and actual tool/action outcomes. "
            "These are AI judgments, not human ratings or Ragas scores.\n\n"
            "**Data:** Fictional development examples. The source, actual answer and reason for each "
            "rating are retained in `data/evaluation/generation_quality.json`. "
            "Normal chat use and opening this page do not trigger scoring or change these results."
        )
        if review:
            st.markdown(f"**Review date:** {review.reviewed_at.strftime('%d %B %Y')}. "
                        f"**Application version:** `{review.source_commit[:7]}`. "
                        f"**Models:** {', '.join(sorted(set(review.models.values())))}.")
            for limitation in review.limitations:
                st.text(limitation)
        for name, _, explanation in CRITERIA:
            st.markdown(f"**{name}:** {explanation}")
            if review:
                dimension = name.lower().replace(" ", "_")
                scored = [case for case in review.cases if case.ratings[dimension].score is not None]
                if scored:
                    example = min(scored, key=lambda case: case.ratings[dimension].score)
                    st.text(f"Review evidence ({example.case_id}): {example.ratings[dimension].reason}")
        if review:
            for case in review.cases:
                for finding in case.critical_findings:
                    st.text(f"Critical finding ({case.case_id}): {finding}")
        st.markdown(
            "**Rating scale:** 0 = fundamental failure; 1 = major errors or omissions; "
            "2 = minor errors or omissions; 3 = fully meets the criterion. "
            "A missing review stays **Not scored**, rather than becoming 0.\n\n"
            "**Weighting:** Each dimension is reported separately. Its mean is the sum of supplied "
            "ratings ÷ the number of rated applicable answers, with equal weight per answer. "
            "Reviewed answers shows that count against all applicable planned answers; missing "
            "outputs/reviews stay in that denominator, and inapplicable dimensions are excluded. "
            "There is no combined generation score or custom weighting between dimensions. "
            "Invented delivery or other critical action claims must be identified explicitly; "
            "high ratings on other dimensions cannot cancel them."
        )
