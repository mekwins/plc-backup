"""
Tests for app.compare.xml_normalizer
"""
import textwrap

import pytest
from lxml import etree

from app.compare.xml_normalizer import normalize_l5x


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _l5x(body: str, extra_root_attrs: str = "") -> bytes:
    """Wrap *body* in a minimal RSLogix5000Content root element."""
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <RSLogix5000Content SchemaRevision="1.0" {extra_root_attrs}>
        {body}
        </RSLogix5000Content>
        """
    ).encode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_round_trip_preserves_content():
    """normalize_l5x on the same bytes twice produces the same output."""
    xml = _l5x("<Controller Name='Test'><Tags /></Controller>")
    first = normalize_l5x(xml)
    second = normalize_l5x(first)
    assert first == second


def test_attribute_sorting():
    """Attributes are sorted alphabetically after normalisation."""
    xml = _l5x("<Item Z='3' A='1' M='2' />")
    normalised = normalize_l5x(xml)
    root = etree.fromstring(normalised)
    item = root.find("Item")
    keys = list(item.attrib.keys())
    assert keys == sorted(keys)


def test_noisy_root_attributes_removed():
    """ExportDate, Owner, and ExportOptions are stripped from the root element."""
    xml = _l5x(
        "<Controller />",
        extra_root_attrs=(
            'ExportDate="Tue Mar 18 10:00:00 2025" '
            'Owner="engineer@plant" '
            'ExportOptions="NoRung"'
        ),
    )
    normalised = normalize_l5x(xml)
    root = etree.fromstring(normalised)
    for attr in ("ExportDate", "Owner", "ExportOptions"):
        assert attr not in root.attrib, f"Noisy attr {attr!r} was not removed"


def test_noisy_child_elements_removed():
    """Child elements tagged ExportDate or ExportOptions are stripped."""
    xml = _l5x(
        """\
        <Controller>
          <ExportDate>Tue Mar 18 10:00:00 2025</ExportDate>
          <ExportOptions>NoRung</ExportOptions>
          <Tags />
        </Controller>
        """
    )
    normalised = normalize_l5x(xml)
    root = etree.fromstring(normalised)
    controller = root.find("Controller")
    assert controller.find("ExportDate") is None
    assert controller.find("ExportOptions") is None
    # Tags element should still be present
    assert controller.find("Tags") is not None


def test_two_equivalent_exports_produce_same_bytes():
    """Two logically identical L5X files differing only in noisy attrs normalise to the same bytes."""
    base_body = "<Controller Name='Line01'><Tags /></Controller>"
    export_a = _l5x(base_body, 'ExportDate="Mon Jan 01 00:00:00 2024" Owner="alice"')
    export_b = _l5x(base_body, 'ExportDate="Tue Jan 02 09:30:00 2024" Owner="bob"')
    assert normalize_l5x(export_a) == normalize_l5x(export_b)


def test_different_logic_produces_different_bytes():
    """Different ladder logic produces different normalised output."""
    xml_a = _l5x("<Controller Name='A'><Tags /></Controller>")
    xml_b = _l5x("<Controller Name='B'><Tags /></Controller>")
    assert normalize_l5x(xml_a) != normalize_l5x(xml_b)


def test_invalid_xml_raises():
    """Malformed XML raises lxml.etree.XMLSyntaxError."""
    with pytest.raises(etree.XMLSyntaxError):
        normalize_l5x(b"<not closed")
