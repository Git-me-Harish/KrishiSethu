"""Unit tests for CSRF token generation and verification."""

from __future__ import annotations

from krishisetu.core.csrf import (
    CSRF_COOKIE,
    CSRF_SIGN_COOKIE,
    generate_csrf_token,
    set_csrf_cookies,
    verify_csrf_token,
)


class TestCsrfTokenGeneration:
    def test_generates_pair(self) -> None:
        token, signature = generate_csrf_token()
        assert isinstance(token, str)
        assert isinstance(signature, str)
        assert len(token) > 20  # base64(32 bytes) ~ 43 chars
        assert len(signature) == 64  # hex(sha256)

    def test_tokens_are_unique(self) -> None:
        t1, _ = generate_csrf_token()
        t2, _ = generate_csrf_token()
        assert t1 != t2  # random


class TestCsrfTokenVerification:
    def test_valid_pair(self) -> None:
        token, signature = generate_csrf_token()
        assert verify_csrf_token(token, signature) is True

    def test_wrong_signature(self) -> None:
        token, _ = generate_csrf_token()
        # Generate a different signature
        _, other_sig = generate_csrf_token()
        assert verify_csrf_token(token, other_sig) is False

    def test_tampered_token(self) -> None:
        token, signature = generate_csrf_token()
        # Flip one character in the token
        tampered = ("A" if token[0] != "A" else "B") + token[1:]
        assert verify_csrf_token(tampered, signature) is False

    def test_empty_inputs(self) -> None:
        assert verify_csrf_token("", "") is False

    def test_constant_time_comparison(self) -> None:
        """The HMAC comparison uses hmac.compare_digest for timing safety."""
        # This is a smoke test — we can't directly test timing in unit tests,
        # but verify the function is consistent across multiple calls.
        token, sig = generate_csrf_token()
        for _ in range(100):
            assert verify_csrf_token(token, sig) is True


class TestSetCsrfCookies:
    def test_sets_both_cookies(self) -> None:
        from starlette.responses import Response

        response = Response()
        token, signature = generate_csrf_token()
        set_csrf_cookies(response, token, signature)

        cookie_headers = [h[1] for h in response.headers.items() if h[0] == "set-cookie"]
        assert any(CSRF_COOKIE in h for h in cookie_headers)
        assert any(CSRF_SIGN_COOKIE in h for h in cookie_headers)

    def test_csrf_cookie_not_httponly(self) -> None:
        """The csrf cookie must be readable by JavaScript (httponly=False)."""
        from starlette.responses import Response

        response = Response()
        token, sig = generate_csrf_token()
        set_csrf_cookies(response, token, sig)

        cookie_headers = [h[1] for h in response.headers.items() if h[0] == "set-cookie"]
        csrf_cookie = next(h for h in cookie_headers if h.startswith(CSRF_COOKIE))
        assert "httponly" not in csrf_cookie.lower()

    def test_sign_cookie_is_httponly(self) -> None:
        """The signature cookie must NOT be readable by JavaScript."""
        from starlette.responses import Response

        response = Response()
        token, sig = generate_csrf_token()
        set_csrf_cookies(response, token, sig)

        cookie_headers = [h[1] for h in response.headers.items() if h[0] == "set-cookie"]
        sign_cookie = next(h for h in cookie_headers if h.startswith(CSRF_SIGN_COOKIE))
        assert "httponly" in sign_cookie.lower()

    def test_cookies_use_samesite_strict(self) -> None:
        from starlette.responses import Response

        response = Response()
        token, sig = generate_csrf_token()
        set_csrf_cookies(response, token, sig)

        cookie_headers = [h[1] for h in response.headers.items() if h[0] == "set-cookie"]
        for h in cookie_headers:
            assert "samesite=strict" in h.lower()
