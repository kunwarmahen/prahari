"""A mail server, small and plain, on a local socket: enough IMAP for
Python's imaplib and an IDLE -- LOGIN, EXAMINE, UID FETCH of headers,
IDLE/DONE, NOOP, CLOSE, LOGOUT. ``deliver`` puts a mail in the folder and
tells every connection that is idling, as a real server does."""

from __future__ import annotations

import re
import socketserver
import threading


class FakeImap:
    def __init__(self, password: str = "app-password", validity: int = 7) -> None:
        self.password = password
        self.validity = validity
        self.mail: list[tuple[int, bytes]] = []
        self.idling: list = []
        self.commands: list[str] = []
        self.lock = threading.Lock()
        self.idle_started = threading.Event()
        fake = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                fake.serve(self)

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def deliver(self, sender: str, subject: str, message_id: str = "") -> int:
        with self.lock:
            uid = (self.mail[-1][0] if self.mail else 0) + 1
            head = (f"From: {sender}\r\nTo: me@example.com\r\nSubject: {subject}\r\n"
                    f"Date: Thu, 22 Oct 2026 09:00:00 +0000\r\n"
                    + (f"Message-ID: {message_id}\r\n" if message_id else "") + "\r\n")
            self.mail.append((uid, head.encode()))
            count = len(self.mail)
            for out in list(self.idling):
                try:
                    out.write(f"* {count} EXISTS\r\n".encode())
                    out.flush()
                except OSError:
                    pass
        return uid

    # -- one connection --------------------------------------------------------

    def serve(self, conn) -> None:
        out = conn.wfile

        def say(line: str) -> None:
            out.write(line.encode() + b"\r\n")
            out.flush()

        say("* OK [CAPABILITY IMAP4rev1 IDLE] fake ready")
        while True:
            raw = conn.rfile.readline()
            if not raw:
                return
            line = raw.decode().rstrip("\r\n")
            tag, _, rest = line.partition(" ")
            verb = rest.split(" ", 1)[0].upper()
            self.commands.append(verb)
            if verb == "CAPABILITY":
                say("* CAPABILITY IMAP4rev1 IDLE")
                say(f"{tag} OK done")
            elif verb == "LOGIN":
                if self.password not in rest:
                    say(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
                else:
                    say(f"{tag} OK signed in")
            elif verb in ("EXAMINE", "SELECT"):
                with self.lock:
                    count = len(self.mail)
                    following = (self.mail[-1][0] if self.mail else 0) + 1
                say(f"* {count} EXISTS")
                say(f"* OK [UIDVALIDITY {self.validity}] ok")
                say(f"* OK [UIDNEXT {following}] ok")
                say(f"{tag} OK [READ-ONLY] opened")
            elif verb == "UID" and " FETCH " in rest.upper():
                start = int(re.search(r"FETCH (\d+):\*", rest, re.I).group(1))
                with self.lock:
                    wanted = [(n, m) for n, m in enumerate(self.mail, 1) if m[0] >= start]
                    if not wanted and self.mail:
                        wanted = [(len(self.mail), self.mail[-1])]
                for seq, (uid, head) in wanted:
                    out.write(f"* {seq} FETCH (UID {uid} BODY[HEADER.FIELDS (FROM TO "
                              f"SUBJECT DATE MESSAGE-ID)] {{{len(head)}}}\r\n".encode())
                    out.write(head + b")\r\n")
                out.flush()
                say(f"{tag} OK fetched")
            elif verb == "IDLE":
                say("+ idling")
                with self.lock:
                    self.idling.append(out)
                self.idle_started.set()
                done = conn.rfile.readline()
                with self.lock:
                    self.idling.remove(out)
                if done.strip().upper() != b"DONE":
                    return
                say(f"{tag} OK idle done")
            elif verb in ("NOOP", "CLOSE"):
                say(f"{tag} OK done")
            elif verb == "LOGOUT":
                say("* BYE")
                say(f"{tag} OK bye")
                return
            else:
                say(f"{tag} BAD unknown")
