"""Tests for DiffParser."""

import pytest

from codesub.diff_parser import DiffParser, ranges_overlap


class TestDiffParser:
    """Tests for DiffParser class."""

    def test_parse_simple_modification(self):
        diff_text = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -2,1 +2,1 @@
-old line
+new line
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        fd = file_diffs[0]
        assert fd.old_path == "test.txt"
        assert fd.new_path == "test.txt"
        assert len(fd.hunks) == 1

        hunk = fd.hunks[0]
        assert hunk.old_start == 2
        assert hunk.old_count == 1
        assert hunk.new_start == 2
        assert hunk.new_count == 1

    def test_parse_insertion(self):
        diff_text = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -2,0 +3,2 @@
+inserted line 1
+inserted line 2
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        hunk = file_diffs[0].hunks[0]
        assert hunk.old_start == 2
        assert hunk.old_count == 0
        assert hunk.new_start == 3
        assert hunk.new_count == 2

    def test_parse_deletion(self):
        diff_text = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -3,2 +3,0 @@
-deleted line 1
-deleted line 2
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        hunk = file_diffs[0].hunks[0]
        assert hunk.old_start == 3
        assert hunk.old_count == 2
        assert hunk.new_start == 3
        assert hunk.new_count == 0

    def test_parse_omitted_counts(self):
        # When count is 1, it can be omitted
        diff_text = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -5 +5 @@
-old
+new
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        hunk = file_diffs[0].hunks[0]
        assert hunk.old_start == 5
        assert hunk.old_count == 1  # Default when omitted
        assert hunk.new_start == 5
        assert hunk.new_count == 1

    def test_parse_multiple_hunks(self):
        diff_text = """diff --git a/test.txt b/test.txt
index 1234567..abcdefg 100644
--- a/test.txt
+++ b/test.txt
@@ -2,1 +2,1 @@
-line 2
+modified line 2
@@ -10,1 +10,1 @@
-line 10
+modified line 10
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        assert len(file_diffs[0].hunks) == 2

        # Hunks should be sorted by old_start
        assert file_diffs[0].hunks[0].old_start == 2
        assert file_diffs[0].hunks[1].old_start == 10

    def test_parse_new_file(self):
        diff_text = """diff --git a/new.txt b/new.txt
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,3 @@
+line 1
+line 2
+line 3
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        assert file_diffs[0].is_new_file is True

    def test_parse_deleted_file(self):
        diff_text = """diff --git a/old.txt b/old.txt
deleted file mode 100644
index 1234567..0000000
--- a/old.txt
+++ /dev/null
@@ -1,3 +0,0 @@
-line 1
-line 2
-line 3
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        assert file_diffs[0].is_deleted_file is True

    def test_parse_rename(self):
        diff_text = """diff --git a/old.txt b/new.txt
similarity index 100%
rename from old.txt
rename to new.txt
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 1
        assert file_diffs[0].old_path == "old.txt"
        assert file_diffs[0].new_path == "new.txt"
        assert file_diffs[0].is_rename is True

    def test_parse_multiple_files(self):
        diff_text = """diff --git a/file1.txt b/file1.txt
index 1234567..abcdefg 100644
--- a/file1.txt
+++ b/file1.txt
@@ -1,1 +1,1 @@
-old
+new
diff --git a/file2.txt b/file2.txt
index 1234567..abcdefg 100644
--- a/file2.txt
+++ b/file2.txt
@@ -5,1 +5,1 @@
-old
+new
"""
        parser = DiffParser()
        file_diffs = parser.parse_patch(diff_text)

        assert len(file_diffs) == 2
        assert file_diffs[0].old_path == "file1.txt"
        assert file_diffs[1].old_path == "file2.txt"

    def test_parse_empty_diff(self):
        parser = DiffParser()
        file_diffs = parser.parse_patch("")

        assert file_diffs == []

    def test_parse_name_status_modifications(self):
        name_status = """M\tfile1.txt
M\tfile2.txt
"""
        parser = DiffParser()
        rename_map, status_map = parser.parse_name_status(name_status)

        assert rename_map == {}
        assert status_map == {"file1.txt": "M", "file2.txt": "M"}

    def test_parse_name_status_rename(self):
        name_status = """R100\told.txt\tnew.txt
M\tother.txt
"""
        parser = DiffParser()
        rename_map, status_map = parser.parse_name_status(name_status)

        assert rename_map == {"old.txt": "new.txt"}
        assert status_map == {"old.txt": "R100", "other.txt": "M"}

    def test_parse_name_status_deletion(self):
        name_status = """D\tdeleted.txt
"""
        parser = DiffParser()
        rename_map, status_map = parser.parse_name_status(name_status)

        assert rename_map == {}
        assert status_map == {"deleted.txt": "D"}


class TestRangesOverlap:
    """Tests for ranges_overlap function."""

    def test_no_overlap_before(self):
        assert ranges_overlap(1, 5, 10, 20) is False

    def test_no_overlap_after(self):
        assert ranges_overlap(10, 20, 1, 5) is False

    def test_overlap_partial_left(self):
        assert ranges_overlap(1, 10, 5, 15) is True

    def test_overlap_partial_right(self):
        assert ranges_overlap(5, 15, 1, 10) is True

    def test_overlap_contained(self):
        assert ranges_overlap(5, 10, 1, 20) is True

    def test_overlap_contains(self):
        assert ranges_overlap(1, 20, 5, 10) is True

    def test_overlap_same(self):
        assert ranges_overlap(5, 10, 5, 10) is True

    def test_overlap_adjacent_touching(self):
        # Ranges touch at one point
        assert ranges_overlap(1, 5, 5, 10) is True

    def test_no_overlap_adjacent(self):
        # Ranges don't touch
        assert ranges_overlap(1, 4, 5, 10) is False
