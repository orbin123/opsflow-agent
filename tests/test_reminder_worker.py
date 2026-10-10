import json
import os
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app.reminders import reminder_worker as worker_module
from app.reminders.reminder_worker import ReminderWorker, WorkerAlreadyRunning
from app.tools import email_notifications as email
from app.tools import reminders


START = datetime(2026, 10, 6, tzinfo=UTC)
DUE = START + timedelta(minutes=1)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(reminders, "load_dotenv", Mock())
    monkeypatch.setattr(worker_module, "load_dotenv", Mock())
    monkeypatch.setattr(email, "load_dotenv", Mock())
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("OPSFLOW_USER_EMAIL", "user@example.com")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "reminders.sqlite3"
    reminders.schedule_reminder("Review SLA", DUE.replace(tzinfo=None), "operation-1",
                                timezone="UTC", now=START, db_path=path)
    return path


@pytest.fixture
def clock():
    return Mock(return_value=DUE)


@pytest.fixture
def sender(monkeypatch):
    def accepted(reminder, attempt_id, *, now):
        return email.NotificationResult(status="accepted", reason=None, message_id=f"<{attempt_id}@opsflow.local>")
    double = Mock(side_effect=accepted)
    monkeypatch.setattr(worker_module, "send_reminder_notification", double)
    return double


def snapshot(db):
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        state = connection.execute("SELECT state FROM reminders ORDER BY reminder_id").fetchone()[0]
        attempts = [dict(row) for row in connection.execute("SELECT * FROM reminder_attempts ORDER BY attempt_no")]
    return state, attempts


def outcome(sender, status, reason, retryable=False):
    sender.side_effect = lambda reminder, attempt_id, **kwargs: email.NotificationResult(
        status=status, reason=reason, message_id=f"<{attempt_id}@opsflow.local>", retryable=retryable,
    )


def test_due_boundary_and_committed_attempt_before_submission(db, clock, sender):
    accepted = sender.side_effect

    def inspect_before_send(reminder, attempt_id, *, now):
        state, attempts = snapshot(db)
        assert state == "submitting"
        assert len(attempts) == 1
        assert attempts[0]["attempt_id"] == attempt_id
        assert attempts[0]["outcome"] == "submitting"
        assert attempts[0]["message_id"] == f"<{attempt_id}@opsflow.local>"
        assert attempts[0]["started_at"] == DUE.isoformat(timespec="microseconds")
        assert attempts[0]["ended_at"] is None
        return accepted(reminder, attempt_id, now=now)

    sender.side_effect = inspect_before_send
    with ReminderWorker(db, clock=clock) as worker:
        clock.return_value = DUE - timedelta(microseconds=1)
        assert worker.run_once() == []
        sender.assert_not_called()
        clock.return_value = DUE
        result = worker.run_once()
        assert result[0]["state"] == result[0]["outcome"] == "accepted"
        assert worker.run_once() == []
    state, attempts = snapshot(db)
    assert state == "accepted"
    assert attempts[0]["ended_at"] == DUE.isoformat(timespec="microseconds")
    assert attempts[0]["reason"] is None
    sender.assert_called_once()
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    sender.assert_called_once()


def test_overdue_pending_reminder_is_processed_after_downtime(db, clock, sender):
    clock.return_value = DUE + timedelta(days=3)
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once()[0]["outcome"] == "accepted"
    assert sender.call_args.kwargs["now"] == clock.return_value
    assert snapshot(db)[0] == "accepted"


@pytest.mark.parametrize("reason", ["timeout", "provider_unavailable"])
def test_retry_delays_budget_and_eligibility_survive_restart(db, clock, sender, reason):
    outcome(sender, "failed", reason, retryable=True)
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once()[0]["state"] == "retry"
        assert worker.run_once() == []
    state, attempts = snapshot(db)
    assert state == "retry"
    assert attempts[0]["next_attempt_at"] == (DUE + timedelta(minutes=1)).isoformat(timespec="microseconds")
    with ReminderWorker(db, clock=clock) as worker:
        clock.return_value = DUE + timedelta(seconds=59)
        assert worker.run_once() == []
        clock.return_value = DUE + timedelta(minutes=1)
        assert worker.run_once()[0]["state"] == "retry"
    assert snapshot(db)[1][-1]["next_attempt_at"] == (DUE + timedelta(minutes=6)).isoformat(timespec="microseconds")
    with ReminderWorker(db, clock=clock) as worker:
        clock.return_value = DUE + timedelta(minutes=6) - timedelta(microseconds=1)
        assert worker.run_once() == []
        clock.return_value = DUE + timedelta(minutes=6)
        assert worker.run_once()[0]["state"] == "failed"
        clock.return_value += timedelta(days=10)
        assert worker.run_once() == []
    state, attempts = snapshot(db)
    assert state == "failed"
    assert [attempt["attempt_no"] for attempt in attempts] == [1, 2, 3]
    assert len({attempt["message_id"] for attempt in attempts}) == 3
    assert attempts[-1]["next_attempt_at"] is None
    assert sender.call_count == 3
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    assert sender.call_count == 3


def test_transient_retry_can_later_be_accepted(db, clock, sender):
    outcome(sender, "failed", "timeout", retryable=True)
    with ReminderWorker(db, clock=clock) as worker:
        worker.run_once()
    outcome(sender, "accepted", None)
    clock.return_value += timedelta(minutes=1)
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once()[0]["state"] == "accepted"
    assert [attempt["outcome"] for attempt in snapshot(db)[1]] == ["failed", "accepted"]


@pytest.mark.parametrize(("status", "reason"), [
    ("failed", "authentication"), ("failed", "configuration"), ("failed", "rejected"),
    ("failed", "provider_unavailable"), ("unknown", "timeout"), ("unknown", "provider_unavailable"),
])
def test_terminal_and_unknown_outcomes_are_not_retried(db, clock, sender, status, reason):
    outcome(sender, status, reason)
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once()[0]["state"] == status
    clock.return_value += timedelta(days=30)
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    assert snapshot(db)[0] == status
    sender.assert_called_once()


def test_unexpected_submission_failure_is_unknown_and_sanitized(db, clock, sender):
    sender.side_effect = RuntimeError("private content and credentials")
    with ReminderWorker(db, clock=clock) as worker:
        result = worker.run_once()
    assert result[0]["state"] == "unknown"
    assert "private" not in json.dumps(result) + json.dumps(snapshot(db))


def test_wrong_message_id_result_is_unknown(db, clock, sender):
    sender.side_effect = lambda *args, **kwargs: email.NotificationResult(
        status="accepted", reason=None, message_id="wrong-id",
    )
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once()[0]["state"] == "unknown"


def test_second_process_cannot_recover_or_submit_while_owner_is_active(db, clock, sender):
    with ReminderWorker(db, clock=clock) as worker:
        # Hold an unfinished attempt; the child must not turn it into unknown.
        assert worker._claim() is not None
        script = """
import sys
from app.reminders.reminder_worker import ReminderWorker, WorkerAlreadyRunning
try:
    with ReminderWorker(sys.argv[1]):
        sys.exit(99)
except WorkerAlreadyRunning:
    sys.exit(7)
"""
        result = subprocess.run([sys.executable, "-c", script, str(db)], cwd=reminders._ROOT,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 7, result.stderr
        assert snapshot(db)[0] == "submitting"
        with pytest.raises(WorkerAlreadyRunning):
            with ReminderWorker(db.parent / "." / db.name):
                pass
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    assert snapshot(db)[0] == "unknown"
    sender.assert_not_called()


def test_recovery_after_actual_process_exit_keeps_claim_unknown(db, clock, sender):
    script = """
import os, socket, sys
from datetime import UTC, datetime
from app.reminders import reminder_worker as module
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError('network forbidden'))
module.send_reminder_notification = lambda *args, **kwargs: os._exit(23)
with module.ReminderWorker(sys.argv[1], clock=lambda: datetime(2026, 10, 6, 0, 1, tzinfo=UTC)) as worker:
    worker.run_once()
"""
    result = subprocess.run([sys.executable, "-c", script, str(db)], cwd=reminders._ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 23, result.stderr
    assert snapshot(db)[0] == "submitting"
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    state, attempts = snapshot(db)
    assert state == "unknown"
    assert attempts[0]["outcome"] == "unknown"
    assert attempts[0]["reason"] == "interrupted"
    assert attempts[0]["ended_at"] is not None
    sender.assert_not_called()


def test_crash_after_acceptance_before_outcome_write_is_not_resubmitted(db, clock, sender, monkeypatch):
    with ReminderWorker(db, clock=clock) as worker:
        monkeypatch.setattr(worker, "_finish", Mock(side_effect=SystemExit(23)))
        with pytest.raises(SystemExit):
            worker.run_once()
        with pytest.raises(RuntimeError, match="healthy"):
            worker.run_once()
    sender.assert_called_once()
    assert snapshot(db)[0] == "submitting"
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    assert snapshot(db)[0] == "unknown"
    sender.assert_called_once()


@pytest.mark.parametrize("stage", ["claim", "outcome"])
def test_commit_failure_prevents_send_or_holds_accepted_attempt_for_recovery(db, clock, sender, monkeypatch, stage):
    original_connect = sqlite3.connect
    with ReminderWorker(db, clock=clock) as worker:
        class FailCommit(sqlite3.Connection):
            def __exit__(self, *args):
                should_fail = stage == "claim" or sender.call_count > 0
                if should_fail:
                    self.rollback()
                    raise sqlite3.OperationalError("private commit failure")
                return super().__exit__(*args)

        monkeypatch.setattr(worker_module.sqlite3, "connect", lambda *args, **kwargs:
                            original_connect(*args, factory=FailCommit, **kwargs))
        with pytest.raises(reminders.ReminderPersistenceError) as error:
            worker.run_once()
        assert "private" not in str(error.value)
        with pytest.raises(RuntimeError, match="healthy"):
            worker.run_once()
        monkeypatch.setattr(worker_module.sqlite3, "connect", original_connect)
    state, attempts = snapshot(db)
    if stage == "claim":
        assert state == "pending" and attempts == []
        sender.assert_not_called()
    else:
        assert state == "submitting" and attempts[0]["outcome"] == "submitting"
        sender.assert_called_once()
        with ReminderWorker(db, clock=clock) as worker:
            assert worker.run_once() == []
        assert snapshot(db)[0] == "unknown"
        sender.assert_called_once()


def test_outcome_failure_stops_before_next_reminder(db, clock, sender, monkeypatch):
    reminders.schedule_reminder("Second task", DUE.replace(tzinfo=None), "operation-2",
                                timezone="UTC", now=START, db_path=db)
    with ReminderWorker(db, clock=clock) as worker:
        monkeypatch.setattr(worker, "_finish", Mock(side_effect=reminders.ReminderPersistenceError("persist failed")))
        with pytest.raises(reminders.ReminderPersistenceError):
            worker.run_once()
    sender.assert_called_once()
    with sqlite3.connect(db) as connection:
        assert sorted(row[0] for row in connection.execute("SELECT state FROM reminders")) == ["pending", "submitting"]


def test_existing_creation_retry_does_not_reset_delivery_state(db, clock, sender):
    with ReminderWorker(db, clock=clock) as worker:
        worker.run_once()
    reminders.schedule_reminder("Review SLA", DUE.replace(tzinfo=None), "operation-1",
                                timezone="UTC", now=DUE + timedelta(days=1), db_path=db)
    assert snapshot(db)[0] == "accepted"
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    sender.assert_called_once()


def test_cli_sigterm_finishes_current_attempt_and_stops_before_next(db, monkeypatch, capsys):
    # Use actual worker/transport; substitute only the current clock and SMTP.
    monkeypatch.setattr(worker_module, "ReminderWorker", lambda path: ReminderWorker(path, clock=lambda: DUE))
    reminders.schedule_reminder("Second task", DUE.replace(tzinfo=None), "operation-2",
                                timezone="UTC", now=START, db_path=db)
    smtp = Mock()
    def send(*args, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        return {}
    smtp.send_message.side_effect = send
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", Mock(return_value=smtp))
    assert worker_module.main(["--db-path", str(db)]) == 0
    smtp.send_message.assert_called_once()
    with sqlite3.connect(db) as connection:
        assert sorted(row[0] for row in connection.execute("SELECT state FROM reminders")) == ["accepted", "pending"]
    output = json.loads(capsys.readouterr().out)
    assert output["outcome"] == "accepted"


def test_cli_failure_is_sanitized_and_signals_restored(db, monkeypatch, capsys):
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(worker_module, "ReminderWorker", Mock(side_effect=reminders.ReminderPersistenceError("private")))
    assert worker_module.main(["--once", "--db-path", str(db)]) == 1
    assert "private" not in capsys.readouterr().out
    assert signal.getsignal(signal.SIGTERM) == previous


def test_cli_once_exits_without_waiting(db, monkeypatch, capsys):
    monkeypatch.setattr(worker_module, "ReminderWorker", lambda path: ReminderWorker(path, clock=lambda: START))
    assert worker_module.main(["--once", "--db-path", str(db)]) == 0
    assert capsys.readouterr().out == ""


def test_reminder_message_uses_original_zone_and_only_configured_recipient(tmp_path, monkeypatch):
    db = tmp_path / "reminders.sqlite3"
    task = "Review SLA\nBcc: external@example.com"
    reminders.schedule_reminder(task, datetime(2026, 10, 6, 5, 31), "operation-1",
                                timezone="Asia/Kolkata", now=START, db_path=db)
    smtp = Mock()
    smtp.send_message.return_value = {}
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", Mock(return_value=smtp))
    with ReminderWorker(db, clock=lambda: DUE + timedelta(days=1)) as worker:
        assert worker.run_once()[0]["outcome"] == "accepted"
    message = smtp.send_message.call_args.args[0]
    assert smtp.send_message.call_args.kwargs == {"from_addr": "sender@gmail.com", "to_addrs": ["user@example.com"]}
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "OpsFlow: reminder due"
    assert message["Bcc"] is None and message["Cc"] is None
    assert message["Message-ID"] == snapshot(db)[1][0]["message_id"]
    body = message.get_content()
    assert "2026-10-06T05:31:00+05:30 [Asia/Kolkata]" in body
    assert task in body
    assert "after its original due time" in body
    assert "Reminder ID:" in body
    assert message.get_content_type() == "text/plain"


@pytest.mark.parametrize(("stage", "failure", "state", "reason"), [
    ("connect", TimeoutError("private"), "retry", "timeout"),
    ("login", email.smtplib.SMTPServerDisconnected("private"), "retry", "provider_unavailable"),
    ("connect", RuntimeError("private"), "failed", "provider_unavailable"),
    ("connect", ssl.SSLCertVerificationError("private"), "failed", "provider_unavailable"),
    ("login", email.smtplib.SMTPAuthenticationError(535, b"private"), "failed", "authentication"),
    ("send", email.smtplib.SMTPDataError(554, b"private"), "failed", "rejected"),
    ("send", TimeoutError("private"), "unknown", "timeout"),
])
def test_real_transport_classification_controls_worker_retry(db, monkeypatch, stage, failure, state, reason):
    smtp = Mock()
    smtp.send_message.return_value = {}
    factory = Mock(return_value=smtp)
    if stage == "connect":
        factory.side_effect = failure
    elif stage == "login":
        smtp.login.side_effect = failure
    else:
        smtp.send_message.side_effect = failure
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", factory)
    with ReminderWorker(db, clock=lambda: DUE) as worker:
        result = worker.run_once()
        assert result[0]["state"] == state
        assert result[0]["reason"] == reason
        assert worker.run_once() == []
    assert snapshot(db)[0] == state
    assert "private" not in json.dumps(snapshot(db))
    factory.assert_called_once()


def test_missing_smtp_configuration_is_terminal_without_connection(db, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD")
    factory = Mock()
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", factory)
    with ReminderWorker(db, clock=lambda: DUE) as worker:
        assert worker.run_once()[0]["reason"] == "configuration"
    assert snapshot(db)[0] == "failed"
    factory.assert_not_called()


def test_sender_rejects_premature_submission_before_connection(db, monkeypatch):
    record = reminders.schedule_reminder("Review SLA", DUE.replace(tzinfo=None), "operation-1",
                                        timezone="UTC", now=START, db_path=db)
    factory = Mock()
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", factory)
    with pytest.raises(ValueError, match="not due"):
        email.send_reminder_notification(record, "00000000-0000-0000-0000-000000000001", now=START)
    factory.assert_not_called()


def test_recovery_write_failure_stops_and_releases_ownership(db, clock, sender):
    with ReminderWorker(db, clock=clock) as worker:
        worker._claim()
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TRIGGER fail_recovery BEFORE UPDATE ON reminder_attempts "
                           "BEGIN SELECT RAISE(ABORT, 'private recovery failure'); END")
    with pytest.raises(reminders.ReminderPersistenceError) as error:
        with ReminderWorker(db, clock=clock):
            pytest.fail("Recovery failure must prevent processing")
    assert "private" not in str(error.value)
    assert snapshot(db)[0] == "submitting"
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TRIGGER fail_recovery")
    with ReminderWorker(db, clock=clock) as worker:
        assert worker.run_once() == []
    assert snapshot(db)[0] == "unknown"
    sender.assert_not_called()
