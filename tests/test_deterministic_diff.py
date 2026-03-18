"""
Tests for app.compare.deterministic_diff
"""
import textwrap

import pytest

from app.compare.deterministic_diff import (
    compute_text_diff,
    compute_xml_sections_diff,
    extract_section,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _l5x(programs: list[str] = None, routines: list[str] = None, tags: list[str] = None) -> bytes:
    prog_xml = "\n".join(
        f'<Program Name="{p}" />' for p in (programs or [])
    )
    routine_xml = "\n".join(
        f'<Routine Name="{r}" />' for r in (routines or [])
    )
    tag_xml = "\n".join(
        f'<Tag Name="{t}" DataType="BOOL" />' for t in (tags or [])
    )
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <RSLogix5000Content>
          <Controller Name="Test">
            {prog_xml}
            {routine_xml}
            {tag_xml}
          </Controller>
        </RSLogix5000Content>
        """
    ).encode()


# ---------------------------------------------------------------------------
# compute_text_diff
# ---------------------------------------------------------------------------

def test_text_diff_identical():
    """Identical strings produce an empty diff."""
    assert compute_text_diff("hello\n", "hello\n") == ""


def test_text_diff_shows_addition():
    diff = compute_text_diff("line1\n", "line1\nline2\n")
    assert "+line2" in diff


def test_text_diff_shows_removal():
    diff = compute_text_diff("line1\nline2\n", "line1\n")
    assert "-line2" in diff


def test_text_diff_labels():
    diff = compute_text_diff("a\n", "b\n", label_a="left.L5X", label_b="right.L5X")
    assert "left.L5X" in diff
    assert "right.L5X" in diff


# ---------------------------------------------------------------------------
# extract_section
# ---------------------------------------------------------------------------

def test_extract_section_returns_programs():
    xml = _l5x(programs=["MainProgram", "SafetyProgram"])
    result = extract_section(xml, "Program")
    names = [r["name"] for r in result]
    assert "MainProgram" in names
    assert "SafetyProgram" in names


def test_extract_section_empty_when_missing():
    xml = _l5x()  # no programs
    result = extract_section(xml, "Program")
    assert result == []


def test_extract_section_has_content_hash():
    xml = _l5x(tags=["Setpoint"])
    result = extract_section(xml, "Tag")
    assert len(result) == 1
    assert len(result[0]["content_hash"]) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------------------
# compute_xml_sections_diff
# ---------------------------------------------------------------------------

def test_sections_diff_no_changes():
    xml = _l5x(programs=["Main"], tags=["Tag1"])
    result = compute_xml_sections_diff(xml, xml)
    for section in result.values():
        assert section["added"] == 0
        assert section["removed"] == 0
        assert section["modified"] == 0


def test_sections_diff_added_program():
    xml_a = _l5x(programs=["Main"])
    xml_b = _l5x(programs=["Main", "NewProgram"])
    result = compute_xml_sections_diff(xml_a, xml_b)
    assert result["programs"]["added"] == 1
    assert "NewProgram" in result["programs"]["added_names"]


def test_sections_diff_removed_tag():
    xml_a = _l5x(tags=["Tag1", "Tag2"])
    xml_b = _l5x(tags=["Tag1"])
    result = compute_xml_sections_diff(xml_a, xml_b)
    assert result["tags"]["removed"] == 1
    assert "Tag2" in result["tags"]["removed_names"]


def test_sections_diff_modified_program():
    xml_a = textwrap.dedent(
        """\
        <?xml version="1.0"?>
        <RSLogix5000Content>
          <Program Name="Main"><Rung Number="0" /></Program>
        </RSLogix5000Content>
        """
    ).encode()
    xml_b = textwrap.dedent(
        """\
        <?xml version="1.0"?>
        <RSLogix5000Content>
          <Program Name="Main"><Rung Number="1" /></Program>
        </RSLogix5000Content>
        """
    ).encode()
    result = compute_xml_sections_diff(xml_a, xml_b)
    assert result["programs"]["modified"] == 1
    assert "Main" in result["programs"]["modified_names"]


def test_sections_diff_result_keys():
    """Result dict contains all expected section keys."""
    xml = _l5x()
    result = compute_xml_sections_diff(xml, xml)
    expected_keys = {"controller", "tasks", "programs", "routines", "aois", "udts", "tags", "modules"}
    assert expected_keys == set(result.keys())
