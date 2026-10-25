# Copyright (C) 2025 OrbVis - License: GNU General Public License v2
"""Object-option catalogues and the label-override choice mapping."""

from app.object_options import (
    LABEL_SHOW_OVERRIDES,
    label_show_override_from_choice,
    label_show_override_to_choice,
)


def test_label_show_override_round_trips_every_choice() -> None:
    for name, _title in LABEL_SHOW_OVERRIDES:
        assert label_show_override_to_choice(label_show_override_from_choice(name)) == name


def test_label_show_override_maps_persisted_values() -> None:
    assert label_show_override_to_choice(True) == "always"
    assert label_show_override_to_choice(False) == "never"
    assert label_show_override_to_choice(None) == "inherit"


def test_label_show_override_treats_unknown_choice_as_inherit() -> None:
    assert label_show_override_from_choice(None) is None
    assert label_show_override_from_choice("nonsense") is None
    # A stray bool from the old checkbox form must not flip captions on.
    assert label_show_override_from_choice(True) is None
