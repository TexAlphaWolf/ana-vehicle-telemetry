from __future__ import annotations

import pytest

from vehicletelemetry.params import ParamError, Params


def test_defaults_are_valid_and_round_trip():
    p = Params()
    assert Params.from_dict(p.as_dict()) == p


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "3"])
def test_rejects_bad_numbers(bad):
    with pytest.raises(ParamError):
        Params(gap_s=bad)


def test_fill_cannot_exceed_gap():
    with pytest.raises(ParamError, match="max_fill_s"):
        Params(gap_s=5, max_fill_s=6)


def test_unknown_parameter():
    with pytest.raises(ParamError, match="unknown"):
        Params.from_dict({"nope": 1})
