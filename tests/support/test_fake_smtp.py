import smtplib
from email.message import EmailMessage

from tests.support.fake_smtp import run_in_thread


def _send(port: int) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "a@x.test", "b@x.test", "hello"
    msg.set_content("body")
    with smtplib.SMTP("127.0.0.1", port, timeout=5) as client:
        client.send_message(msg)


def test_fake_smtp_captures_and_can_fail_next():
    sink = run_in_thread()
    try:
        _send(sink.port)
        assert [m["Subject"] for m in sink.messages] == ["hello"]
        sink.fail_next(1)
        try:
            _send(sink.port)
            raise AssertionError("expected a 451")
        except smtplib.SMTPException:
            pass
        _send(sink.port)
        assert len(sink.messages) == 2
    finally:
        sink.stop()
