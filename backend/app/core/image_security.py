"""Image content validation — magic-byte checks and SVG XML sandboxing.

These helpers reject uploads that lie about their Content-Type, and — for SVGs —
block the usual XXE / billion-laughs footguns by parsing with defusedxml.
"""

from __future__ import annotations

import re

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

# Icons are rendered as-is in the board. GIF is intentionally excluded — we
# don't want animated icons flickering in map overviews.
ICON_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/svg+xml", "image/webp"})
ICON_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".webp"})

# Background images of static boards may include GIF — a common legacy
# asset format for imported maps.
BACKGROUND_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp"}
)
BACKGROUND_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})

# Raster magic bytes
_PNG_MAGIC = b"\x89PNG"
_JPEG_MAGIC = b"\xff\xd8\xff"
_GIF_MAGIC = (b"GIF87a", b"GIF89a")
_WEBP_RIFF = b"RIFF"
_WEBP_MARK = b"WEBP"


# Real-world SVGs (Illustrator/Inkscape exports) often carry an XML
# declaration, a DOCTYPE, and licence comments before the root element, so the
# sniff window has to be generous — a 512-byte window missed those exports.
_SVG_SNIFF_BYTES = 65536


def _looks_like_svg_header(content: bytes) -> bool:
    """Quick byte-level sniff — presence of '<svg' in the leading bytes."""
    return b"<svg" in content[:_SVG_SNIFF_BYTES].lower()


# SVG elements / attributes that can execute scripts. Rejected even though
# defusedxml accepts them — once an SVG sits under /images and is opened with
# image/svg+xml, scripts run with the application's origin (XSS). ``use`` is
# *not* blanket-rejected (internal `#fragment` references are both safe and
# common); instead its href is constrained below.
# SMIL animation elements are included: <set>/<animate*> can rewrite an href to
# a ``javascript:`` URI at runtime, and <handler> binds script.
# iframe/object/embed carry their own subresource (srcdoc/data/src) and can run
# script; the walk matches on the namespace-stripped local name, so listing them
# also catches a foreign-namespace smuggle (``<x:iframe>``).
# Lowercase and matched against the lowercased tag: an SVG parsed in an HTML
# context has its tag names case-folded, so a case variant must not slip through.
_SVG_FORBIDDEN_TAGS = frozenset(
    {
        "script",
        "foreignobject",
        "iframe",
        "object",
        "embed",
        "set",
        "animate",
        "animatetransform",
        "animatemotion",
        "handler",
    }
)
_SVG_FORBIDDEN_ATTR_PREFIXES = ("on",)

# Schemes that can execute or read local resources — never allowed in any href.
_DANGEROUS_URI_SCHEMES = ("javascript:", "vbscript:", "file:")
# Browsers drop ASCII whitespace and control chars from a URL before resolving
# its scheme, so ``java&#9;script:`` runs as ``javascript:``. The XML parser
# keeps the character reference as a literal control char and ``strip()`` only
# touches the ends, so every C0 control / space goes before the comparison.
_URL_IGNORED_CHARS = re.compile(r"[\x00-\x20]")
# data: URIs are allowed only for embedded raster images. text/html and
# image/svg+xml data URIs can carry script, so they stay rejected.
_SAFE_DATA_URI_PREFIXES = (
    "data:image/png",
    "data:image/jpeg",
    "data:image/jpg",
    "data:image/gif",
    "data:image/webp",
)

# Elements whose href pulls an external subresource: <use> clones a referenced
# fragment, <image>/<feImage> fetch an image. A remote target turns an icon into
# a tracker / client-side SSRF and, for <use>, can pull in and run external SVG.
_SVG_LOCAL_HREF_ONLY_TAGS = frozenset({"use", "image", "feimage"})

# CSS in a <style> block or style attribute can pull external resources via
# @import, url(...) or the functions that take a plain string URL
# (image-set("…" 1x), image(), cross-fade(), src()), leaking the viewer's IP and
# enabling CSS exfiltration. Local url(#gradient) / url(data:...) paints stay
# allowed.
_CSS_EXTERNAL_REF = re.compile(
    r"@import"
    r"|url\(\s*['\"]?\s*(?:https?:|//|file:)"
    r"|(?:image-set|image|cross-fade|src)\([^{}]*?['\"]\s*(?:https?:|//|file:)",
    re.IGNORECASE,
)
# The browser decodes escapes and drops comments before it tokenises CSS, so
# ``@\69mport`` or ``url(\68ttps://…)`` would slip past the raw-text match.
_CSS_COMMENT = re.compile(r"/\*.*?(?:\*/|$)", re.DOTALL)
# One left-to-right pass like the CSS tokenizer: in ``\\\\e`` the backslashes
# pair up, so a hex-first pass would misread the last ``\e`` as an escape.
_CSS_ESCAPE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\n\r\f]?|(.))", re.DOTALL)
# What survives the decoding still goes through the browser's URL parser, which
# drops tabs and newlines and reads a backslash as a slash: ``ht<TAB>tps:`` is
# ``https:`` and ``\\evil.example`` is ``//evil.example``.
_URL_DROPPED_CHARS = re.compile(r"[\t\n\r]")

# ElementTree drops processing instructions, so the element walk never sees a
# ``<?xml-stylesheet ...?>`` — yet the stored bytes keep it, and a browser opening
# the .svg directly applies the referenced XSLT, which can emit script in our
# origin. Only the XML declaration itself (target ``xml``) is allowed.
_XML_PI_TARGET = re.compile(rb"<\?\s*([^\s?>]+)")


def _href_is_safe(value: str, *, local_only: bool) -> bool:
    """Whether an href / xlink:href value is safe for a sandboxed SVG icon."""
    v = value.strip()
    low = _URL_IGNORED_CHARS.sub("", v).lower()
    if low.startswith(_DANGEROUS_URI_SCHEMES):
        return False
    if low.startswith("data:"):
        # Only embedded rasters; svg+xml/text data URIs could carry script.
        return low.startswith(_SAFE_DATA_URI_PREFIXES)
    if local_only:
        return v.startswith("#")
    return True


def _decode_css_escape(m: re.Match[str]) -> str:
    if m.group(1) is None:
        return m.group(2)
    cp = int(m.group(1), 16)
    return chr(cp) if 0 < cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF else "\ufffd"


def _css_has_external_ref(css: str) -> bool:
    decoded = _CSS_ESCAPE.sub(_decode_css_escape, css)
    decoded = _URL_DROPPED_CHARS.sub("", decoded).replace("\\", "/")
    # Both variants: stripping a "/*" that sits inside a string would otherwise
    # hide a real reference after it.
    return any(_CSS_EXTERNAL_REF.search(v) for v in (decoded, _CSS_COMMENT.sub("", decoded)))


def _has_unsafe_processing_instruction(content: bytes) -> bool:
    """True if *content* carries any XML PI other than the ``<?xml?>`` declaration."""
    return any(m.group(1).lower() != b"xml" for m in _XML_PI_TARGET.finditer(content))


def is_safe_svg(content: bytes) -> bool:
    """Parse *content* as SVG with defusedxml; reject script vectors.

    Must be called only after a byte-level ``<svg`` sniff — defusedxml parses any
    well-formed XML, but only a real ``<svg>`` root element is acceptable here.

    A DOCTYPE is permitted (the standard SVG DTD reference is ubiquitous in
    exported assets) but ``forbid_entities``/``forbid_external`` stay on, so
    billion-laughs entity expansion and XXE external entities are still blocked.
    The parsed tree is then walked to reject script-capable elements, on-event
    attributes, remote ``<use>``/``<image>`` targets, external CSS references,
    script-bearing URIs, and any processing instruction but ``<?xml?>``.
    """
    # The PI scan below works on raw bytes, so only ASCII-compatible encodings
    # are accepted; a UTF-16 body would hide ``<?xml-stylesheet?>`` from it.
    if b"\x00" in content:
        return False
    parser = DefusedET.DefusedXMLParser(
        forbid_dtd=False, forbid_entities=True, forbid_external=True
    )
    try:
        parser.feed(content)
        root = parser.close()
    except (DefusedXmlException, DefusedET.ParseError):
        return False
    if root.tag.rsplit("}", 1)[-1] != "svg":
        return False
    if _has_unsafe_processing_instruction(content):
        return False
    for elem in root.iter():
        local_tag = elem.tag.rsplit("}", 1)[-1].lower()
        if local_tag in _SVG_FORBIDDEN_TAGS:
            return False
        # itertext(), not .text: a child inside <style> pushes the rest into its
        # tail, so ``<style><x/>@import url(…)</style>`` would otherwise slip past.
        if local_tag == "style" and _css_has_external_ref("".join(elem.itertext())):
            return False
        local_only = local_tag in _SVG_LOCAL_HREF_ONLY_TAGS
        for attr_name, attr_val in elem.attrib.items():
            local_attr = attr_name.rsplit("}", 1)[-1].lower()
            if local_attr.startswith(_SVG_FORBIDDEN_ATTR_PREFIXES):
                return False
            # Not only ``style``: presentation attributes (fill, filter, mask,
            # clip-path, marker-*) take a url() paint reference as well.
            if _css_has_external_ref(attr_val):
                return False
            if local_attr == "href" and not _href_is_safe(attr_val, local_only=local_only):
                return False
    return True


def is_valid_image(content: bytes, *, allow_svg: bool = True, allow_gif: bool = True) -> bool:
    """True if *content* starts with a recognised raster header or is a safe SVG.

    ``allow_gif=False`` for icon uploads — ICON_MIME_TYPES excludes GIF (no
    animated icons), and without the flag a GIF body with a faked PNG
    Content-Type would slip through the magic-byte check.
    """
    if not content:
        return False
    head = content[:16]
    if head[:4] == _PNG_MAGIC:
        return True
    if head[:3] == _JPEG_MAGIC:
        return True
    if allow_gif and head[:6] in _GIF_MAGIC:
        return True
    if head[:4] == _WEBP_RIFF and content[8:12] == _WEBP_MARK:
        return True
    if allow_svg and _looks_like_svg_header(content):
        return is_safe_svg(content)
    return False
