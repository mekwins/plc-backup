"""
Deterministic diff utilities for PLC backup comparison.

Provides both a plain-text unified diff and a structured XML section diff
that reports added/removed/modified counts per logical PLC section.
"""
from __future__ import annotations

import difflib
import hashlib
import logging
from typing import Any, Dict, List

from lxml import etree

logger = logging.getLogger(__name__)

# Logical sections present in a standard L5X export
_L5X_SECTIONS = [
    "Controller",
    "Tasks",
    "Programs",
    "Routines",
    "AddOnInstructionDefinitions",
    "DataTypes",
    "Tags",
    "Modules",
]

# Mapping of human-friendly section names to L5X element tags
_SECTION_TAG_MAP: Dict[str, str] = {
    "controller": "Controller",
    "tasks": "Task",
    "programs": "Program",
    "routines": "Routine",
    "aois": "AddOnInstructionDefinition",
    "udts": "DataType",
    "tags": "Tag",
    "modules": "Module",
}


# ---------------------------------------------------------------------------
# Text diff
# ---------------------------------------------------------------------------

def compute_text_diff(content_a: str, content_b: str, label_a: str = "left", label_b: str = "right") -> str:
    """
    Return a unified diff string between *content_a* and *content_b*.

    Parameters
    ----------
    content_a, content_b:
        Text strings to compare (typically L5X file contents).
    label_a, label_b:
        Labels used in the diff header lines.
    """
    lines_a = content_a.splitlines(keepends=True)
    lines_b = content_b.splitlines(keepends=True)
    diff = difflib.unified_diff(
        lines_a,
        lines_b,
        fromfile=label_a,
        tofile=label_b,
        lineterm="",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# XML section diff
# ---------------------------------------------------------------------------

def extract_section(xml_bytes: bytes, tag: str) -> List[Dict[str, Any]]:
    """
    Parse *xml_bytes* and return all elements whose local tag matches *tag*.

    Each element is represented as a dict with:
    - ``name``: value of the ``Name`` attribute (or ``_index_{i}`` if absent)
    - ``attributes``: dict of all attributes
    - ``content_hash``: SHA-256 of the element's serialised text (sorted attrs)

    Parameters
    ----------
    xml_bytes:
        Raw XML bytes.
    tag:
        Element tag to search for (case-sensitive, without namespace prefix).
    """
    try:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        logger.error("Failed to parse XML for section extraction: %s", exc)
        return []

    results = []
    for i, el in enumerate(root.iter()):
        local_tag = etree.QName(el.tag).localname if isinstance(el.tag, str) else None
        if local_tag != tag:
            continue
        name = el.attrib.get("Name", f"_index_{i}")
        attrs = dict(sorted(el.attrib.items()))
        # Hash the element content for change detection
        serialised = etree.tostring(el, encoding="unicode", method="xml")
        content_hash = hashlib.sha256(serialised.encode()).hexdigest()
        results.append(
            {
                "name": name,
                "attributes": attrs,
                "content_hash": content_hash,
            }
        )
    return results


def compute_xml_sections_diff(
    xml_a: bytes,
    xml_b: bytes,
) -> Dict[str, Dict[str, Any]]:
    """
    Compare two L5X XML payloads section by section.

    Returns a dict keyed by section name with sub-keys:
    - ``added``: count of elements present in B but not A
    - ``removed``: count of elements present in A but not B
    - ``modified``: count of elements present in both but with different content
    - ``unchanged``: count of identical elements
    - ``added_names``: list of added element names
    - ``removed_names``: list of removed element names
    - ``modified_names``: list of modified element names

    Parameters
    ----------
    xml_a, xml_b:
        Raw L5X XML bytes for the left and right sides of the comparison.
    """
    result: Dict[str, Dict[str, Any]] = {}

    for section_key, tag in _SECTION_TAG_MAP.items():
        items_a = {item["name"]: item["content_hash"] for item in extract_section(xml_a, tag)}
        items_b = {item["name"]: item["content_hash"] for item in extract_section(xml_b, tag)}

        names_a = set(items_a)
        names_b = set(items_b)
        common = names_a & names_b

        added_names = sorted(names_b - names_a)
        removed_names = sorted(names_a - names_b)
        modified_names = sorted(
            name for name in common if items_a[name] != items_b[name]
        )
        unchanged_count = sum(
            1 for name in common if items_a[name] == items_b[name]
        )

        result[section_key] = {
            "added": len(added_names),
            "removed": len(removed_names),
            "modified": len(modified_names),
            "unchanged": unchanged_count,
            "added_names": added_names,
            "removed_names": removed_names,
            "modified_names": modified_names,
        }

    return result
