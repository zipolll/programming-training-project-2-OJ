"""Regressions for loopback reconnections and private problem navigation data."""

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from frontend import session, session_cache
from frontend.api_client import ApiClient
from frontend.data_access import invalidate_problem_cache, load_problem_detail
from frontend.errors import ApiError


def test_localhost_reconnects_over_ipv4_without_changing_cookie_host(monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.headers["Host"], self.headers.get("Cookie")))
            body = json.dumps({"code": 200, "msg": "success", "data": {}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "session_id=test-only; Path=/; HttpOnly")
            # Reconnect on every request, exercising the same path as an idle
            # connection that the backend has closed between page changes.
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        resolve = socket.getaddrinfo
        connect = socket.socket.connect
        attempted_families = []

        def ipv6_first(host, service, *args, **kwargs):
            if host == "localhost":
                return [
                    (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                     ("::1", int(service), 0, 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                     ("127.0.0.1", int(service))),
                ]
            return resolve(host, service, *args, **kwargs)

        def record_connect(sock, address):
            if address[1] == port:
                attempted_families.append(sock.family)
            return connect(sock, address)

        monkeypatch.setattr(socket, "getaddrinfo", ipv6_first)
        monkeypatch.setattr(socket.socket, "connect", record_connect)
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("NO_PROXY", "")
        client = ApiClient(f"http://localhost:{port}/api")
        try:
            client.get_health()
            client.get_health()
            assert attempted_families == [socket.AF_INET, socket.AF_INET]
            assert seen == [
                (f"localhost:{port}", None),
                (f"localhost:{port}", "session_id=test-only"),
            ]
        finally:
            client.close()
            server.shutdown()
            thread.join(timeout=2)


def test_problem_navigation_cache_is_session_local_and_invalidated_after_save(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={
            "code": 200, "msg": "success",
            "data": {"id": "p1", "revision": len(calls), "testcases": []},
        })

    client = ApiClient("http://test/api", transport=httpx.MockTransport(handler))
    first_session = {}
    second_session = {}
    try:
        monkeypatch.setattr(session_cache.st, "session_state", first_session)
        assert load_problem_detail(client, "p1")["revision"] == 1
        assert load_problem_detail(client, "p1")["revision"] == 1
        monkeypatch.setattr(session_cache.st, "session_state", second_session)
        assert load_problem_detail(client, "p1")["revision"] == 2
        monkeypatch.setattr(session_cache.st, "session_state", first_session)
        invalidate_problem_cache()
        assert load_problem_detail(client, "p1")["revision"] == 3
        assert calls == ["/api/problems/p1"] * 3
    finally:
        client.close()


@pytest.mark.parametrize("authenticated", [False, True])
def test_unauthorized_only_schedules_browser_clear_for_an_existing_identity(
    monkeypatch, authenticated,
):
    def handler(_request):
        return httpx.Response(401, json={"code": 401, "msg": "unauthorized", "data": None})

    monkeypatch.setenv("OJ_FRONTEND_API_BASE_URL", "http://localhost:8000/api")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_kw: httpx.MockTransport(handler))
    state = {"auth_user": {"id": 1} if authenticated else None}
    client = session.get_api_client(state)
    try:
        with pytest.raises(ApiError):
            client.post("/auth/login")
        assert session.current_user(state) is None
        assert (state.get(session.BRIDGE_ACTION_KEY) == "clear") is authenticated
    finally:
        client.close()
