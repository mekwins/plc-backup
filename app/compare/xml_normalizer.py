"""
L5X XML normalizer.

Removes non-deterministic metadata (export timestamps, owner info) and
canonicalises the XML so that byte-for-byte identical program logic produces
identical output regardless of who exported it or when.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Set

from lxml import etree

logger = logging.getLogger(__name__)

# Attribute names on the root RSLogix5000Content element that change on every
# export and should be stripped before any comparison or hashing.
_NOISY_ROOT_ATTRIBUTES: Set[str] = {
    "ExportDate",
    "ExportOptions",
    "Owner",
    "TargetName",
    "TargetType",
    "ContainsContext",
}

# Element tag names that are export-time noise and carry no program logic.
_NOISY_ELEMENT_TAGS: Set[str] = {
    "ExportDate",
    "ExportOptions",
}


def normalize_l5x(content: bytes) -> bytes:
    """
    Normalise an L5X file so that logically equivalent exports produce
    identical bytes.

    Steps applied:
    1. Parse with lxml (strict).
    2. Remove known noisy root-level attributes.
    3. Remove known noisy child elements.
    4. Sort every element's attributes alphabetically by name.
    5. Strip insignificant inter-element whitespace.
    6. Re-serialise using lxml's C14N (canonical XML) for deterministic output.

    Parameters
    ----------
    content:
        Raw bytes of an L5X file.

    Returns
    -------
    bytes
        Normalised canonical XML bytes.
    """
    try:
        parser = etree.XMLParser(remove_blank_text=True, recover=False)
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as exc:
        logger.error("Failed to parse L5X XML: %s", exc)
        raise

    # --- 1. Strip noisy root attributes ---
    for attr in _NOISY_ROOT_ATTRIBUTES:
        root.attrib.pop(attr, None)

    # --- 2. Walk the tree and apply normalisations ---
    _walk_and_normalize(root)

    # --- 3. Serialise to canonical XML bytes ---
    buf = BytesIO()
    root.getroottree().write_c14n(buf, exclusive=False, with_comments=False)
    return buf.getvalue()


def _walk_and_normalize(element: etree._Element) -> None:
    """
    Recursively normalise *element* in-place:
    - Sort attributes alphabetically.
    - Remove noisy child elements.
    - Recurse into remaining children.
    """
    # Sort attributes: lxml stores them in insertion order; we rebuild them.
    if element.attrib:
        sorted_attrs = sorted(element.attrib.items())
        element.attrib.clear()
        for k, v in sorted_attrs:
            element.attrib[k] = v

    # Remove noisy child elements (iterate a copy to avoid mutation issues)
    for child in list(element):
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else None
        if tag in _NOISY_ELEMENT_TAGS:
            element.remove(child)
        else:
            _walk_and_normalize(child)
