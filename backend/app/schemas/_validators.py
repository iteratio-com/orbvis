"""Shared validators for user-supplied URL fields on boards/presentations."""

from __future__ import annotations

import re

# Allowlist instead of a scheme blocklist: browsers strip ASCII control
# characters when parsing URLs, so "java\tscript:alert(1)" bypasses any
# startswith("javascript:") check yet still executes on click. Rejecting
# control characters outright and allowlisting schemes closes that class.
# Beyond the web schemes, monitoring boards traditionally link remote-access
# handlers on host objects (NagVis heritage) — those are user-mediated OS
# handlers, not script-capable, so they stay allowed.
# Keep in sync with SAFE_URL_SCHEMES in frontend/src/utils/sanitize.ts.
_ALLOWED_URL_SCHEMES = frozenset(
    {"http", "https", "mailto", "tel", "ssh", "telnet", "rdp", "vnc", "ftp"}
)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_URL_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")


# A click-through link may open a new tab or stay in the same frame. _top,
# _parent or a named frame would let an object link replace the whole Checkmk
# UI with an external page (phishing).
_ALLOWED_URL_TARGETS = frozenset({"_blank", "_self"})


def coerce_url_target(value: object) -> object:
    """Fold any link target other than ``_blank``/``_self`` to ``_blank``.

    Coerces rather than rejects so boards stored with ``_top`` keep loading.
    """
    if value is None or value == "":
        return value
    if isinstance(value, str) and value in _ALLOWED_URL_TARGETS:
        return value
    return "_blank"


def validate_user_url(value: str | None) -> str | None:
    """Allow scheme-less (relative) URLs plus the allowlisted schemes."""
    if not value:
        return value
    if len(value) > 4096:
        raise ValueError("URL too long")
    s = value.strip()
    if _CONTROL_CHARS.search(s):
        raise ValueError("URL must not contain control characters")
    m = _URL_SCHEME.match(s)
    if m and m.group(1).lower() not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme {m.group(1)!r} is not allowed")
    return s


def coerce_user_url(value: object) -> object:
    """Sanitize now-invalid URLs to ``None`` so legacy boards still load.

    Read-side companion to ``validate_user_url``, same contract as
    ``_coerce_color``: stored JSON may pre-date the allowlist; dropping the
    offending URL keeps the board loadable while API saves stay strict.
    """
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        return None
    try:
        return validate_user_url(value)
    except ValueError:
        return None


# Icon and background references are uploaded filenames the frontend expands
# into an images/ or boards/backgrounds/ asset URL. A separator, ``..`` or a
# scheme would let the reference climb out of the asset directory and turn a
# viewer's page load into a same-origin GET (e.g. ``../../check_mk/logout.py``).
_ASSET_REF_UNSAFE = re.compile(r"[/\\:\x00-\x1f\x7f]|\.\.")


def validate_asset_ref(value: str | None) -> str | None:
    """Accept a bare asset filename; reject anything that could leave its directory."""
    if not value:
        return value
    if len(value) > 255 or _ASSET_REF_UNSAFE.search(value):
        raise ValueError("Image reference must be a plain filename")
    return value


def coerce_asset_ref(value: object) -> object:
    """Read-side companion to ``validate_asset_ref``: drop an unsafe stored reference."""
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        return None
    try:
        return validate_asset_ref(value)
    except ValueError:
        return None
