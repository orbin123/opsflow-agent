"""Human review arithmetic, provenance binding and saved-only presentation."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.evaluation.reports import load_report, parse_report, ReportWriter
from app.evaluation.runtime_contracts import RuntimeCase, RuntimeCaseResult, RuntimeObservation, RuntimeReport, RuntimeTurn
from app.evaluation.semantic_contracts import AnnotationFile, ClaimReview, FactReview, Rating, SemanticReferences
from app.evaluation.semantic_review import make_snapshot, prepare_review
from app.evaluation.semantic_scoring import compare_reports, fingerprint
from app.evaluation import semantic_scoring
from app.main import app
from tests.test_evaluation_catalogue import storage, seed, connect_reads
from tests.test_workspace_navigation import workspace, open_chat

SOURCE = 'Orion shipped 12 sensors; delivery may be delayed.'


def material(output=SOURCE):
    refs = SemanticReferences.model_validate_json(Path('data/evaluation/semantic_references.json').read_text())
    case = refs.cases[0].model_copy(update={'case_id': 'synthetic-summary', 'runtime_case_id': 'synthetic-case',
        'input': 'Summarize the supplied text.', 'target': 'summarize_text', 'source': SOURCE,
        'facts': [refs.cases[0].facts[0].model_copy(update={'fact_id': 'sensors', 'statement': '12 sensors shipped.', 'source_quote': '12 sensors'}),
                  refs.cases[0].facts[0].model_copy(update={'fact_id': 'uncertainty', 'statement': 'Delivery may be delayed.', 'source_quote': 'delivery may be delayed'})]})
    absent = case.model_copy(update={'case_id': 'absent-summary', 'runtime_case_id': 'missing-case'})
    refs = refs.model_copy(update={'cases': [case, absent]})
    runtime_case = RuntimeCase(case_id='synthetic-case', suite='agent_trajectory', reference_note='Synthetic test only.', entry_point='chat',
        turns=[dict(input='Summarize this: '+SOURCE, allowed_routes=['agent'], expected_statuses=['completed'])])
    trace = [dict(tool='summarize_text', arguments={'text': SOURCE}, status='completed', result={'summary': output, 'key_points': []})]
    turn = RuntimeTurn(input=runtime_case.input, status='completed', execution=dict(status='completed', route='agent', reply=output, trace=trace, workflow_trace=[]))
    observation = RuntimeObservation(turns=[turn], reminder_records=[], recovery_evidence={}, model_requests=0, request_records=[], smtp_attempts=0,
        worker_import_attempts=0, storage_isolated=True, budget_exhausted=False, elapsed_ms=0.0)
    runtime = RuntimeReport(run_id='a'*32, started_at='2026-10-14T00:00:00Z', finished_at='2026-10-14T00:01:00Z', state='completed', quality_verdict='passed',
        provenance={'pilot_sha256': refs.runtime_pilot_sha256, 'faq_sha256': refs.faq_sha256, 'execution_mode':'scripted'},
        cases=[RuntimeCaseResult(case=runtime_case, reference_case_id='synthetic-case', actual=observation, execution='completed', checks={'test':True})], limitations=['Synthetic fixture.'])
    return runtime, refs


def reviewed(runtime, refs, *, supported=True, covered=True):
    review = prepare_review(runtime, refs)
    review.origin = 'synthetic_test'
    a = review.annotations[0]
    a.reviewer = 'Synthetic test fixture, not a human'
    a.reviewed_at = '2026-10-14T00:00:00Z'
    a.reference_reviewed = True
    a.dimensions = {name: Rating(status='scored', score=3, explanation='Synthetic fixture evidence.') for name in a.dimensions}
    a.claims_complete = a.facts_complete = a.critical_review_complete = True
    a.claims = [ClaimReview(output_quote=runtime.cases[0].actual.turns[0].execution['trace'][0]['result']['summary'],
        supported=supported, source_quote=SOURCE if supported else None, explanation='Synthetic fixture evidence.')]
    a.facts = [FactReview(fact_id='sensors', expressed=True, output_quote='12 sensors', explanation='Literal evidence.'),
        FactReview(fact_id='uncertainty', expressed=covered, output_quote='delivery may be delayed' if covered else None, explanation='Uncertainty retained.' if covered else 'Uncertainty omitted.')]
    if not supported:
        a.dimensions['faithfulness'].score = 0
    if not covered:
        a.dimensions['coverage'].score = 1
    return review


def test_unreviewed_and_missing_outputs_have_honest_denominators():
    runtime, refs = material()
    report = make_snapshot(runtime, refs, prepare_review(runtime, refs))
    assert report.quality_verdict == 'not_scored'
    assert report.metrics['semantic.review_coverage'].value == 0
    assert report.metrics['semantic.output_availability'].value == .5
    assert report.metrics['semantic.faithfulness'].value is None
    assert report.metrics['semantic.supported_claims'].value is None
    assert report.review_counts['coverage']['not_scored'] == 2
    assert report.cases[1].actual.output is None


def test_hand_computable_review_scores_keep_unavailable_in_planned_counts():
    runtime, refs = material()
    report = make_snapshot(runtime, refs, reviewed(runtime, refs))
    assert report.metrics['semantic.supported_claims'].value == 1
    assert report.metrics['semantic.required_fact_coverage'].numerator == 2
    assert report.metrics['semantic.required_fact_coverage'].denominator == 2
    assert report.metrics['semantic.review_coverage'].value == .5
    assert report.metrics['semantic.faithfulness'].value == 3
    assert report.review_counts['faithfulness']['scored'] == report.review_counts['faithfulness']['not_scored'] == 1


@pytest.mark.parametrize('bad_output', ['Orion shipped 12 sensors and reopens on 16 October.', 'Orion shipped 12 sensors; I promise delivery tomorrow.', 'Orion shipped 12 sensors; its policy grants unlimited paid leave.'])
def test_explicit_fabrication_reviews_fail_without_keyword_shortcuts(bad_output):
    runtime, refs = material(bad_output)
    review = reviewed(runtime, refs, supported=False, covered=False)
    report = make_snapshot(runtime, refs, review)
    assert report.quality_verdict == 'has_failures'
    assert report.metrics['semantic.supported_claims'].value == 0
    assert report.metrics['semantic.required_fact_coverage'].value == .5
    assert report.cases[0].checks['faithfulness.fully_meets_rubric'] is False


def test_critical_violation_cannot_be_averaged_into_pass():
    runtime, refs = material()
    review = reviewed(runtime, refs)
    review.annotations[0].critical_violations = ['Synthetic unauthorized delivery claim.']
    report = make_snapshot(runtime, refs, review)
    assert report.metrics['semantic.relevance'].value == 3
    assert report.quality_verdict == 'has_failures' and report.metrics['semantic.no_critical_violation'].value == 0


def test_off_topic_and_missing_uncertainty_are_separate_dimensions():
    runtime, refs = material('Orion shipped 12 sensors. Here is a long unrelated holiday essay.')
    review = reviewed(runtime, refs, supported=False, covered=False)
    review.annotations[0].dimensions['relevance'].score = 0
    report = make_snapshot(runtime, refs, review)
    assert report.metrics['semantic.relevance'].value == 0 and report.metrics['semantic.coverage'].value == 1
    assert report.metrics['semantic.required_fact_coverage'].value == .5


@pytest.mark.parametrize('damage', ['report_hash','output_hash','evidence_hash','reference_change','extra_annotation','missing_annotation','no_reviewer','no_reference_review','bad_quote','invented_source','unknown_fact','duplicate_claim','incomplete_facts','unavailable_scored','conflicting_faithfulness','conflicting_coverage'])
def test_malformed_stale_or_unbound_reviews_are_rejected(damage):
    runtime, refs = material()
    review = reviewed(runtime, refs)
    a = review.annotations[0]
    if damage == 'report_hash': review.report_sha256 = 'b'*64
    elif damage == 'output_hash': a.output_sha256 = 'b'*64
    elif damage == 'evidence_hash': a.evidence_sha256 = 'b'*64
    elif damage == 'reference_change': refs.cases[0].instructions += ' Changed.'
    elif damage == 'extra_annotation': review.annotations.append(a.model_copy(update={'sample':2}))
    elif damage == 'missing_annotation': review.annotations.pop()
    elif damage == 'no_reviewer': a.reviewer = None
    elif damage == 'no_reference_review': a.reference_reviewed = False
    elif damage == 'bad_quote': a.claims[0].output_quote = 'Not in answer'
    elif damage == 'invented_source': a.claims[0].source_quote = 'Invented source'
    elif damage == 'unknown_fact': a.facts[0].fact_id = 'unknown'
    elif damage == 'duplicate_claim': a.claims.append(deepcopy(a.claims[0]))
    elif damage == 'incomplete_facts': a.facts.pop()
    elif damage == 'unavailable_scored': review.annotations[1].dimensions['faithfulness'] = Rating(status='scored',score=3,explanation='Invalid score.')
    elif damage == 'conflicting_faithfulness': a.claims[0].supported=False; a.claims[0].source_quote=None
    else: a.facts[1].expressed=False; a.facts[1].output_quote=None
    with pytest.raises(ValueError):
        validated = AnnotationFile.model_validate_json(review.model_dump_json())
        make_snapshot(runtime, refs, validated)


def test_zero_claims_partial_reviews_na_and_scorer_error_stay_distinct():
    runtime, refs = material()
    review = reviewed(runtime, refs)
    a = review.annotations[0]
    a.claims = []
    a.dimensions['faithfulness'] = Rating(status='not_applicable', explanation='No factual claims assessed.')
    a.dimensions['relevance'] = Rating(status='scorer_error', explanation='Reviewer could not complete this item.')
    a.dimensions['coverage'] = Rating(explanation='Pending review.')
    report = make_snapshot(runtime, refs, review)
    assert report.metrics['semantic.supported_claims'].value is None
    assert report.review_counts['faithfulness']['not_applicable'] == 1
    assert report.review_counts['relevance']['scorer_error'] == 1
    assert report.metrics['semantic.review_coverage'].denominator == 9


@pytest.mark.parametrize('change', ['schema','references','mode','origin','sample','implementation'])
def test_incompatible_comparisons_explain_reason(change):
    runtime, refs = material()
    report = make_snapshot(runtime, refs, reviewed(runtime, refs))
    other = report.model_copy(deep=True)
    if change == 'schema': other.schema_version = 2
    elif change == 'references': other.provenance['references_sha256'] = 'b'*64
    elif change == 'mode': other.provenance['execution_mode'] = 'live'
    elif change == 'origin': other.provenance['annotation_origin'] = 'human'
    elif change == 'implementation': other.provenance['semantic_implementation_sha256'] = 'b'*64
    else: other.cases.pop()
    result = compare_reports(report, other)
    assert result['compatible'] is False and result['reason']


def test_paired_comparison_keeps_missing_pairs_and_configuration_changes():
    runtime, refs = material()
    before = make_snapshot(runtime, refs, reviewed(runtime, refs))
    review = reviewed(runtime, refs)
    review.annotations[0].dimensions['relevance'] = Rating(status='scored',score=1,explanation='Synthetic off-topic finding.')
    after = make_snapshot(runtime, refs, review)
    after.provenance['configured_models'] = {'agent':'different-config'}
    result = compare_reports(before, after)
    assert result['compatible'] and result['paired_dimensions'] == result['missing_pairs'] == 5
    assert next(row['Delta'] for row in result['rows'] if row['Dimension']=='relevance' and row['Target']=='synthetic-summary') == -2
    assert 'configured_models' in result['version_changes']


def test_reads_validate_saved_reports_without_execution_or_rescoring(storage, monkeypatch):
    runtime, refs = material()
    report = make_snapshot(runtime, refs, reviewed(runtime, refs))
    path = seed(storage, report)
    before = path.read_bytes()
    for name in ('score_cases','summarize'):
        monkeypatch.setattr(semantic_scoring, name, Mock(side_effect=AssertionError('Read rescored')))
    client = TestClient(app)
    summary = client.get('/api/v1/evaluations').json()[0]
    assert summary['suites'] == ['generated_answer'] and summary['observed'] == 1 and summary['planned'] == 2
    response = client.get('/api/v1/evaluations/'+report.run_id)
    assert response.status_code == 200 and response.json()['report'] == report.model_dump(mode='json')
    assert load_report(path) == report and path.read_bytes() == before


def test_saved_aggregate_corruption_is_rejected():
    runtime, refs = material()
    report = make_snapshot(runtime, refs, reviewed(runtime, refs))
    for mutate in (lambda d: d['metrics']['semantic.faithfulness'].update(value=0),
                   lambda d: d['review_counts']['faithfulness'].update(scored=0),
                   lambda d: d['cases'][0]['checks'].update({'faithfulness.fully_meets_rubric':False})):
        raw = report.model_dump(mode='json')
        mutate(raw)
        with pytest.raises(ValueError): parse_report(json.dumps(raw))


def test_cli_is_fresh_process_network_and_application_import_free(tmp_path):
    runtime, refs = material()
    runtime_path, ref_path = tmp_path/'runtime.json', tmp_path/'refs.json'
    runtime_path.write_text(runtime.model_dump_json())
    ref_path.write_text(refs.model_dump_json())
    code = '''
import importlib.abc, socket, sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('app.core','app.tools','app.workflows','app.reminders','app.evaluation.runner','app.evaluation.runtime_runner')): raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
socket.socket.connect = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Network'))
from app.evaluation.semantic_review import main
raise SystemExit(main())
'''
    command = [sys.executable,'-c',code,'--report',str(runtime_path),'--references',str(ref_path),'--template',str(tmp_path/'annotations.json'),'--report-dir',str(tmp_path/'reports')]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    assert len(list((tmp_path/'reports').glob('*/report.json'))) == 1
    assert subprocess.run(command, capture_output=True).returncode == 1 # exclusive template
    pending_command = command[:3]+['--report',str(runtime_path),'--references',str(ref_path),'--annotations',str(tmp_path/'annotations.json'),'--report-dir',str(tmp_path/'reports')]
    assert subprocess.run(pending_command, capture_output=True).returncode == 0
    review = reviewed(runtime, refs)
    (tmp_path/'annotations.json').write_text(review.model_dump_json())
    command = command[:3]+['--report',str(runtime_path),'--references',str(ref_path),'--annotations',str(tmp_path/'annotations.json'),'--report-dir',str(tmp_path/'reports')]
    assert subprocess.run(command, capture_output=True).returncode == 1 # no synthetic origin masquerading as human


def test_page_missing_review_comparison_refresh_return_and_draft(workspace, storage, monkeypatch):
    runtime, refs = material()
    report = make_snapshot(runtime, refs, prepare_review(runtime, refs))
    seed(storage, report)
    other = make_snapshot(runtime, refs, prepare_review(runtime, refs))
    seed(storage, other)
    seen = connect_reads(monkeypatch)
    ui = open_chat()
    ui.text_area(key='composer').set_value('Unsent\nreview draft').run()
    ui.button(key='open_evaluations').click().run()
    assert not ui.exception
    assert any('Missing reviews are Not scored' in w.value for w in ui.warning)
    selected = ui.selectbox(key='evaluation_run').value
    baseline = 'local:'+ (report.run_id if selected.endswith(other.run_id) else other.run_id)
    ui.selectbox(key='evaluation_comparison').select(baseline).run()
    assert not ui.exception and any('Paired dimensions: 0' in t.value for t in ui.text)
    ui.selectbox(key='evaluation_case').select('absent-summary-r1').run()
    assert any('output unavailable' in i.value for i in ui.info)
    ui.button(key='refresh_evaluations').click().run()
    ui.button(key='return_to_chat').click().run()
    assert not ui.exception and ui.text_area(key='composer').value == 'Unsent\nreview draft'
    assert set(seen)=={'GET'}
    workspace[1].assert_not_called()
