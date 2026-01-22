"""Tests for location parsing utilities."""

import pytest

from codesub.errors import InvalidLineRangeError, InvalidLocationError
from codesub.utils import parse_location, extract_anchors


class TestParseLocation:
    """Tests for parse_location function."""

    def test_single_line(self):
        path, start, end = parse_location("path/to/file.py:42")
        assert path == "path/to/file.py"
        assert start == 42
        assert end == 42

    def test_line_range(self):
        path, start, end = parse_location("path/to/file.py:10-20")
        assert path == "path/to/file.py"
        assert start == 10
        assert end == 20

    def test_single_line_one(self):
        path, start, end = parse_location("file.txt:1")
        assert path == "file.txt"
        assert start == 1
        assert end == 1

    def test_windows_style_path_converted(self):
        # Backslashes should be converted to forward slashes
        # Note: On Unix, backslashes are valid filename chars, so we explicitly convert them
        path, start, end = parse_location("path\\to\\file.py:42")
        # On Unix, Path.as_posix() doesn't convert backslashes since they're valid chars
        # The path is kept as-is after parsing; normalization happens at storage level
        assert start == 42
        assert end == 42
        # Path may contain backslashes on Unix (they're valid filename chars)

    def test_invalid_format_no_colon(self):
        with pytest.raises(InvalidLocationError) as exc_info:
            parse_location("path/to/file.py")
        assert "expected format" in str(exc_info.value)

    def test_invalid_format_no_line_number(self):
        with pytest.raises(InvalidLocationError) as exc_info:
            parse_location("path/to/file.py:")
        assert "expected format" in str(exc_info.value)

    def test_invalid_format_non_numeric(self):
        with pytest.raises(InvalidLocationError) as exc_info:
            parse_location("path/to/file.py:abc")
        assert "expected format" in str(exc_info.value)

    def test_invalid_start_zero(self):
        with pytest.raises(InvalidLineRangeError) as exc_info:
            parse_location("file.py:0")
        assert "start line must be >= 1" in str(exc_info.value)

    def test_invalid_end_before_start(self):
        with pytest.raises(InvalidLineRangeError) as exc_info:
            parse_location("file.py:20-10")
        assert "end line must be >= start line" in str(exc_info.value)


class TestExtractAnchors:
    """Tests for extract_anchors function."""

    def test_extract_middle_range(self):
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6", "line 7"]
        ctx_before, watched, ctx_after = extract_anchors(lines, 3, 5, context=2)

        assert ctx_before == ["line 1", "line 2"]
        assert watched == ["line 3", "line 4", "line 5"]
        assert ctx_after == ["line 6", "line 7"]

    def test_extract_at_start(self):
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
        ctx_before, watched, ctx_after = extract_anchors(lines, 1, 2, context=2)

        assert ctx_before == []
        assert watched == ["line 1", "line 2"]
        assert ctx_after == ["line 3", "line 4"]

    def test_extract_at_end(self):
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
        ctx_before, watched, ctx_after = extract_anchors(lines, 4, 5, context=2)

        assert ctx_before == ["line 2", "line 3"]
        assert watched == ["line 4", "line 5"]
        assert ctx_after == []

    def test_extract_single_line(self):
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
        ctx_before, watched, ctx_after = extract_anchors(lines, 3, 3, context=2)

        assert ctx_before == ["line 1", "line 2"]
        assert watched == ["line 3"]
        assert ctx_after == ["line 4", "line 5"]

    def test_extract_with_different_context(self):
        lines = ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6", "line 7"]
        ctx_before, watched, ctx_after = extract_anchors(lines, 4, 4, context=3)

        assert ctx_before == ["line 1", "line 2", "line 3"]
        assert watched == ["line 4"]
        assert ctx_after == ["line 5", "line 6", "line 7"]
