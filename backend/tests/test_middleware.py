"""Unit tests for the pure origin-matching helpers in ``app.core.middleware``.

``CSRFOriginMiddleware`` itself is exercised end-to-end in ``test_csrf.py``;
here we pin down the host-normalisation and same-origin logic directly,
including the reverse-proxy precedence and IPv6/port edge cases that are hard
to provoke through the HTTP layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient

from app.core.middleware import RequestBodyLimitMiddleware, _host_only, is_same_origin


def _headers(**named: str) -> Iterable[tuple[bytes, bytes]]:
    """Build ASGI raw headers (lowercased byte names) from keyword args."""
    return [(name.replace("_", "-").encode(), value.encode()) for name, value in named.items()]


class TestHostOnly:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("example.com", "example.com"),
            ("example.com:8422", "example.com"),
            ("EXAMPLE.COM", "example.com"),
            ("Example.Com:443", "example.com"),
            ("  example.com  ", "example.com"),
            ("a.example.com, b.example.com", "a.example.com"),
            ("first.com:80, second.com", "first.com"),
        ],
    )
    def test_plain_hosts(self, value: str, expected: str) -> None:
        assert _host_only(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("[::1]", "[::1]"),
            ("[::1]:8080", "[::1]"),
            ("[2001:DB8::1]:443", "[2001:db8::1]"),
            ("[fe80::1]", "[fe80::1]"),
        ],
    )
    def test_ipv6_brackets(self, value: str, expected: str) -> None:
        assert _host_only(value) == expected

    def test_unterminated_bracket_falls_back_to_lowercased_whole(self) -> None:
        assert _host_only("[BROKEN") == "[broken"


class TestIsSameOrigin:
    def test_matches_host_header(self) -> None:
        assert is_same_origin("https://example.com", _headers(host="example.com"))

    def test_matches_host_header_ignoring_port(self) -> None:
        assert is_same_origin("https://example.com", _headers(host="example.com:8422"))

    def test_forwarded_host_takes_precedence_over_host(self) -> None:
        # The backend Host carries the upstream port; X-Forwarded-Host is the
        # public name the browser actually used.
        headers = _headers(host="127.0.0.1:8422", x_forwarded_host="orbvis.example.com")
        assert is_same_origin("https://orbvis.example.com", headers)

    def test_forwarded_host_mismatch_still_checks_host(self) -> None:
        headers = _headers(host="orbvis.example.com:8422", x_forwarded_host="proxy.internal")
        assert is_same_origin("https://orbvis.example.com", headers)

    def test_forwarded_host_chain_uses_first_entry(self) -> None:
        headers = _headers(x_forwarded_host="orbvis.example.com, proxy.internal")
        assert is_same_origin("https://orbvis.example.com", headers)

    def test_foreign_origin_is_rejected(self) -> None:
        assert not is_same_origin("https://evil.example.com", _headers(host="orbvis.example.com"))

    def test_empty_origin_is_rejected(self) -> None:
        assert not is_same_origin("", _headers(host="example.com"))

    def test_origin_without_host_is_rejected(self) -> None:
        # A bare scheme has no hostname to compare against.
        assert not is_same_origin("null", _headers(host="example.com"))

    def test_no_relevant_headers_is_rejected(self) -> None:
        assert not is_same_origin("https://example.com", _headers(accept="text/html"))

    def test_case_insensitive_host_match(self) -> None:
        assert is_same_origin("https://Example.COM", _headers(host="example.com"))


class TestRequestBodyLimit:
    @staticmethod
    def _client(limit: int) -> TestClient:
        app = FastAPI()

        @app.post("/echo")
        async def echo(request: Request) -> dict[str, int]:
            return {"size": len(await request.body())}

        @app.post("/form")
        async def form(file: UploadFile = File(...)) -> dict[str, int]:
            return {"size": len(await file.read())}

        app.add_middleware(RequestBodyLimitMiddleware, max_body_size=limit)
        return TestClient(app)

    def test_body_within_limit_passes(self) -> None:
        resp = self._client(100).post("/echo", content=b"x" * 100)
        assert resp.status_code == 200
        assert resp.json() == {"size": 100}

    def test_declared_length_over_limit_is_refused(self) -> None:
        resp = self._client(100).post("/echo", content=b"x" * 101)
        assert resp.status_code == 413

    def test_chunked_body_over_limit_is_refused(self) -> None:
        def chunks() -> Iterator[bytes]:
            for _ in range(5):
                yield b"x" * 40

        resp = self._client(100).post("/echo", content=chunks())
        assert resp.status_code == 413

    def test_multipart_upload_over_limit_is_refused(self) -> None:
        resp = self._client(1000).post("/form", files={"file": ("a.png", b"x" * 2000)})
        assert resp.status_code == 413
