"""Unit tests for input sanitization helpers."""

from __future__ import annotations

import pytest

from krishisetu.core.input_sanitizer import (
    InputValidationError,
    detect_sql_injection_attempt,
    sanitize_filename,
    sanitize_free_text,
    sanitize_name,
    sanitize_sql_like,
    sanitize_url,
)


class TestSanitizeFreeText:
    def test_strips_control_chars(self) -> None:
        text = "hello\x00world\x07done"
        cleaned = sanitize_free_text(text)
        assert "\x00" not in cleaned
        assert "\x07" not in cleaned
        assert "hello" in cleaned and "world" in cleaned

    def test_preserves_newlines_and_tabs(self) -> None:
        text = "line1\nline2\ttabbed"
        cleaned = sanitize_free_text(text)
        assert "\n" in cleaned
        assert "\t" in cleaned

    def test_blocks_script_tag(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_free_text("<script>alert(1)</script>")

    def test_blocks_iframe(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_free_text('<iframe src="evil.com"></iframe>')

    def test_blocks_javascript_url(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_free_text("javascript:alert(1)")

    def test_blocks_onclick_handler(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_free_text('<img onclick="alert(1)">')

    def test_truncates_long_input(self) -> None:
        long_text = "A" * 20_000
        cleaned = sanitize_free_text(long_text, max_length=100)
        assert len(cleaned) <= 100
        assert cleaned.endswith("\u2026")  # ellipsis

    def test_unicode_normalization(self) -> None:
        # NFC: composed form (é = single codepoint) vs decomposed (e + acute accent)
        decomposed = "caf\u0065\u0301"  # e + combining acute
        composed = "café"  # é as single codepoint
        assert sanitize_free_text(decomposed) == composed

    def test_none_returns_empty(self) -> None:
        assert sanitize_free_text(None) == ""


class TestSanitizeName:
    def test_valid_name(self) -> None:
        assert sanitize_name("Rajesh Kumar") == "Rajesh Kumar"
        assert sanitize_name("O'Brien") == "O'Brien"
        assert sanitize_name("Dr. Smith") == "Dr. Smith"
        assert sanitize_name("Mary-Jane") == "Mary-Jane"

    def test_unicode_name(self) -> None:
        # Hindi name
        assert sanitize_name("राजेश कुमार") == "राजेश कुमार"

    def test_rejects_html(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_name("<script>alert(1)</script>")

    def test_rejects_digits(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_name("Rajesh123")

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_name("Rajesh@#$")

    def test_max_length(self) -> None:
        long_name = "A" * 300
        with pytest.raises(InputValidationError):
            sanitize_name(long_name)


class TestSanitizeFilename:
    def test_strips_path_traversal(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_filename("../../etc/passwd")
        with pytest.raises(InputValidationError):
            sanitize_filename("..\\..\\windows\\system32")
        with pytest.raises(InputValidationError):
            sanitize_filename("%2e%2e%2fpasswd")

    def test_strips_directory_components(self) -> None:
        # Should return basename only
        assert sanitize_filename("/tmp/upload.jpg") == "upload.jpg"
        assert sanitize_filename("C:\\Users\\test\\file.txt") == "file.txt"

    def test_blocks_hidden_files(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_filename(".env")
        with pytest.raises(InputValidationError):
            sanitize_filename(".gitignore")

    def test_replaces_unsafe_chars(self) -> None:
        result = sanitize_filename("file;name&with|bad*chars.jpg")
        assert ";" not in result
        assert "&" not in result
        assert "|" not in result
        assert "*" not in result

    def test_preserves_extension(self) -> None:
        result = sanitize_filename("photo.JPG")
        assert result.endswith(".JPG") or result.endswith(".jpg")

    def test_empty_filename_raises(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_filename("")

    def test_max_length(self) -> None:
        long_name = "A" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 255


class TestSanitizeSqlLike:
    def test_escapes_percent(self) -> None:
        assert sanitize_sql_like("100%") == "100\\%"

    def test_escapes_underscore(self) -> None:
        assert sanitize_sql_like("user_1") == "user\\_1"

    def test_escapes_backslash(self) -> None:
        assert sanitize_sql_like("path\\to") == "path\\\\to"

    def test_none_returns_empty(self) -> None:
        assert sanitize_sql_like(None) == ""


class TestDetectSqlInjection:
    def test_detects_or_1_1(self) -> None:
        assert detect_sql_injection_attempt("' OR 1=1") is True
        assert detect_sql_injection_attempt("' OR '1'='1") is True

    def test_detects_union_select(self) -> None:
        assert detect_sql_injection_attempt("1 UNION SELECT NULL") is True

    def test_detects_drop_table(self) -> None:
        assert detect_sql_injection_attempt("; DROP TABLE users") is True

    def test_detects_information_schema(self) -> None:
        assert detect_sql_injection_attempt("information_schema.tables") is True

    def test_does_not_flag_legitimate_text(self) -> None:
        assert detect_sql_injection_attempt("Hello world") is False
        assert detect_sql_injection_attempt("Plot 12.5 acres") is False
        assert detect_sql_injection_attempt("Rajesh Kumar") is False

    def test_handles_none_and_empty(self) -> None:
        assert detect_sql_injection_attempt(None) is False
        assert detect_sql_injection_attempt("") is False


class TestSanitizeUrl:
    def test_https_url(self) -> None:
        result = sanitize_url("https://example.com/path")
        assert result.startswith("https://")

    def test_http_url(self) -> None:
        result = sanitize_url("http://example.com")
        assert result.startswith("http://")

    def test_rejects_javascript_url(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_url("javascript:alert(1)")

    def test_rejects_data_url(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_url("data:text/html,<script>alert(1)</script>")

    def test_rejects_ftp_url(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_url("ftp://files.example.com")

    def test_custom_allowed_schemes(self) -> None:
        result = sanitize_url("ftp://files.example.com", allowed_schemes=("ftp",))
        assert result.startswith("ftp://")

    def test_empty_raises(self) -> None:
        with pytest.raises(InputValidationError):
            sanitize_url("")
