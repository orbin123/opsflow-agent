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
    ("Faithfulness", "Facts are supported by the source."),
    ("Coverage", "Required facts and uncertainty are included."),
    ("Relevance", "The answer addresses the request."),
    ("Instruction compliance", "Requested format, tone and constraints are followed."),
    ("Status accuracy", "Completed, failed and scheduled work is described correctly."),
    ("Context relevance", "The right source or conversation context is used."),
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
    for name, _ in CRITERIA:
        result = scores.get(name.lower().replace(" ", "_"))
        rows.append({"Dimension": name,
                     "Rating (0–3)": f"{result['mean']:.2f}" if result and result["mean"] is not None else "Not scored",
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
        st.markdown("**Method**\n\nWord TF-IDF turns request text into features. "
                    "A calibrated linear SVM predicts one of eight intents.")
        if report is not None:
            st.markdown(
                f"**Data**\n\n{report.dataset.row_count:,} fictional labelled requests: "
                f"{report.split.development_rows:,} development examples and "
                f"{report.split.test_rows:,} holdout examples, split proportionally across intents."
            )
        else:
            st.markdown("**Data**\n\nThe saved classifier results are unavailable.")
        st.markdown(
            "**Metrics**\n\n"
            "- **Accuracy:** Correct predictions ÷ all test examples.\n"
            "- **Precision:** Correct predictions of an intent ÷ all predictions of that intent.\n"
            "- **Recall:** Correct predictions of an intent ÷ all examples of that intent.\n"
            "- **F1:** 2 × precision × recall ÷ (precision + recall); zero if both are zero.\n"
            "- **Support:** Number of test examples for an intent.\n\n"
            "**Weighting**\n\nMacro averages give each intent equal weight (12.5%). "
            "Weighted averages use each intent's share of test examples. "
            "They coincide when all intents have equal support."
        )
        if report is not None:
            st.markdown(f"**View**\n\nResults recorded on {report.created_on.strftime('%d %B %Y')} "
                        "for the fictional holdout. Opening this page does not rerun or retrain the model.")
    st.subheader("Generation quality")
    try:
        review = get_generation_review(base_url)
    except ChatClientError as exc:
        review = None
        st.error(str(exc))
    if review:
        available = sum(bool(c.answer and c.answer.strip()) for c in review.cases)
        st.caption(f"Automated sample review · {available} of {len(review.cases)} planned answers available.")
        findings = [finding for case in review.cases for finding in case.critical_findings]
        if findings:
            st.warning(f"The review identified {len(findings)} critical finding(s). See the explanation below.")
    st.table(generation_rows(review), hide_index=True,
             alt="Generation quality sample ratings and reviewed versus applicable answer counts")
    with st.expander("How generation quality is assessed"):
        st.markdown("**Method**\n\nCompare each answer with its request, source facts, "
                    "relevant context and actual task outcomes.")
        if review:
            st.markdown(f"**Data**\n\n{len(review.cases)} fictional test cases; {available} answers available. "
                        "Unavailable answers remain in the counts. "
                        f"Reviewed on {review.reviewed_at.strftime('%d %B %Y')}.")
        else:
            st.markdown("**Data**\n\nThe saved sample review is unavailable. Missing ratings stay Not scored.")
        st.markdown("**Checks**\n\n" + "\n".join(
            f"- **{name}:** {meaning}" for name, meaning in CRITERIA))
        st.markdown(
            "**Scoring**\n\n"
            "- **0:** Fundamental failure.\n"
            "- **1:** Major errors or omissions.\n"
            "- **2:** Minor errors or omissions.\n"
            "- **3:** Fully meets the criterion.\n\n"
            "**Weighting**\n\nEach rating is the mean of scored, applicable answers, "
            "with equal weight per answer. Reviewed answers shows scored ÷ applicable planned answers. "
            "Missing answers stay in that count; inapplicable checks are excluded. "
            "There is no combined generation score.\n\n"
            "**View**\n\nSaved automated sample ratings. "
            "Normal chat use does not recalculate them. "
            "A small fictional sample does not establish overall model reliability."
        )
        if review:
            gaps = [case for case in review.cases if case.application_status == "completed"
                    and case.ratings["status_accuracy"].score is not None
                    and case.ratings["status_accuracy"].score < 3]
            if gaps:
                st.markdown("**Finding**")
                for case in gaps:
                    if case.case_id == "missing_applicability":
                        st.markdown("Contractor eligibility needed clarification, but the application "
                                    "marked the answer as completed. This reduced the status accuracy rating.")
                    else:
                        st.text(case.ratings["status_accuracy"].reason)
            for case in review.cases:
                for finding in case.critical_findings:
                    st.markdown("**Critical finding**")
                    st.text(finding)
