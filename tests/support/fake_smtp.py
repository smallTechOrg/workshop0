"""A real local SMTP sink (aiosmtpd) so email tests talk SMTP over a socket, never a third party.

In pytest::

    from tests.support.fake_smtp import run_in_thread
    smtp = run_in_thread()              # port 0 = pick a free port
    smtp.port, smtp.messages            # captured messages (email.message.Message)
    smtp.fail_next(2)                   # reject the next 2 deliveries with 451
    smtp.stop()

As a process (the e2e gate)::

    uv run python tests/support/fake_smtp.py --port 8025

Plain SMTP, no TLS and no auth: point the app at it with WORKSHOP0_SMTP_HOST=127.0.0.1,
WORKSHOP0_SMTP_PORT=<port>, WORKSHOP0_SMTP_STARTTLS=false and any user/password.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import Message

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, AuthResult, Envelope, LoginPassword, Session


@dataclass
class Captured:
    mail_from: str
    rcpt_tos: list[str]
    message: Message
    raw: bytes


class _Handler:
    def __init__(self, sink: "FakeSMTP") -> None:
        self._sink = sink

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        with self._sink._lock:
            if self._sink._failures_left > 0:
                self._sink._failures_left -= 1
                return "451 Requested action aborted: simulated failure"
            raw = envelope.original_content or envelope.content or b""
            self._sink.captured.append(
                Captured(envelope.mail_from, list(envelope.rcpt_tos), message_from_bytes(raw), raw)
            )
        return "250 OK"


def _accept_any_auth(server, session, envelope, mechanism, auth_data) -> AuthResult:
    return AuthResult(success=True)


@dataclass
class FakeSMTP:
    host: str = "127.0.0.1"
    port: int = 0
    captured: list[Captured] = field(default_factory=list)
    _controller: Controller | None = None
    _failures_left: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def messages(self) -> list[Message]:
        return [c.message for c in self.captured]

    def fail_next(self, count: int = 1) -> None:
        with self._lock:
            self._failures_left = count

    def clear(self) -> None:
        with self._lock:
            self.captured.clear()
            self._failures_left = 0

    def start(self) -> "FakeSMTP":
        if self.port == 0:
            with socket.socket() as probe:  # aiosmtpd cannot report an ephemeral port reliably
                probe.bind((self.host, 0))
                self.port = probe.getsockname()[1]
        # auth_required=False + auth_require_tls=False: accept (and ignore) AUTH if offered.
        self._controller = Controller(
            _Handler(self),
            hostname=self.host,
            port=self.port,
            auth_require_tls=False,
            auth_required=False,
            authenticator=_accept_any_auth,
        )
        self._controller.start()
        return self

    def stop(self) -> None:
        if self._controller is not None:
            self._controller.stop()
            self._controller = None


def run_in_thread(port: int = 0, host: str = "127.0.0.1") -> FakeSMTP:
    return FakeSMTP(host=host, port=port).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake SMTP sink for Workshop0 tests/e2e")
    parser.add_argument("--port", type=int, default=8025)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    sink = run_in_thread(args.port, args.host)
    print(f"fake smtp listening on {sink.host}:{sink.port}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        sink.stop()


if __name__ == "__main__":
    main()
