from __future__ import annotations

import io
import math

import numpy as np
import pytest

from vehicletelemetry import logio
from vehicletelemetry.logio import LogError, parse_csv, to_csv


def parse(text: str, **kw):
    return parse_csv(io.StringIO(text), **kw)


def test_round_trip_is_exact(demo):
    log, _ = demo
    back = parse(to_csv(log))
    assert back.t0 == log.t0
    assert np.array_equal(back.t, log.t)
    for c in ("speed", "rpm", "throttle", "load", "coolant", "fuel"):
        assert np.array_equal(back.channel(c), log.channel(c), equal_nan=True)


def test_minimal_file_and_missing_values():
    log = parse(
        "time,speed_kmh\n2027-01-01T10:00:00,10\n2027-01-01T10:00:01,\n2027-01-01T10:00:02,nan\n2027-01-01T10:00:03,12.5\n"
    )
    assert list(log.t) == [0.0, 1.0, 2.0, 3.0]
    assert math.isnan(log.speed[1]) and math.isnan(log.speed[2]) and log.speed[3] == 12.5
    assert log.present() == {
        "speed": True,
        "rpm": False,
        "throttle": False,
        "load": False,
        "coolant": False,
        "fuel": False,
    }


def test_aliases_case_and_epoch_seconds():
    log = parse("Timestamp,Speed,Engine_RPM\n1700000000,50,2000\n1700000001.5,51,2100\n")
    assert list(log.t) == [0.0, 1.5]
    assert list(log.rpm) == [2000.0, 2100.0]


def test_time_zone_is_converted_to_utc():
    log = parse("time,speed_kmh\n2027-01-01T12:00:00+02:00,1\n2027-01-01T10:00:01Z,2\n")
    assert log.t0.hour == 10 and list(log.t) == [0.0, 1.0]


def test_maf_becomes_fuel_flow():
    log = parse(
        "time,speed_kmh,maf_gs\n2027-01-01T10:00:00,50,10\n2027-01-01T10:00:01,50,20\n", afr=14.7, density_g_l=745.0
    )
    assert log.fuel[0] == pytest.approx(10 * 3600 / (14.7 * 745.0))
    assert log.fuel[1] == pytest.approx(2 * log.fuel[0])


def test_fuel_column_wins_over_maf():
    log = parse("time,speed_kmh,maf_gs,fuel_lph\n2027-01-01T10:00:00,50,10,3\n2027-01-01T10:00:01,50,20,4\n")
    assert list(log.fuel) == [3.0, 4.0]


def test_blank_lines_and_bom_are_tolerated(tmp_path):
    f = tmp_path / "a.csv"
    f.write_bytes(b"\xef\xbb\xbftime,speed_kmh\n\n2027-01-01T10:00:00,1\n,\n2027-01-01T10:00:01,2\n")
    assert len(logio.read_csv(f)) == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("time\n2027-01-01T10:00:00\n", "at least time and speed_kmh"),
        ("time,speed_kmh,speed\n2027-01-01T10:00:00,1,1\n", "repeats"),
        ("time,speed_kmh\n2027-01-01T10:00:00,1\n", "two rows"),
        ("time,speed_kmh\n2027-01-01T10:00:00,1,2\n2027-01-01T10:00:01,1\n", "line 2: 3 fields"),
        ("time,speed_kmh\n2027-01-01T10:00:00,abc\n2027-01-01T10:00:01,1\n", "line 2: cannot read 'abc'"),
        ("time,speed_kmh\nyesterday,1\n2027-01-01T10:00:01,1\n", "as a time"),
        ("time,speed_kmh\n2027-01-01T10:00:01,1\n2027-01-01T10:00:00,1\n", "line 3: time"),
        ("time,speed_kmh\n2027-01-01T10:00:01,1\n2027-01-01T10:00:01,1\n", "does not come after"),
        ("time,speed_kmh\nnan,1\n2027-01-01T10:00:01,1\n", "as a time"),
        ("time,speed_kmh\n1e30,1\n1e30,2\n", "out of range"),
    ],
)
def test_errors_name_the_line(text, message):
    with pytest.raises(LogError, match=message):
        parse(text)


def test_missing_and_binary_files(tmp_path):
    with pytest.raises(LogError, match="cannot read"):
        logio.read_csv(tmp_path / "nope.csv")
    f = tmp_path / "b.csv"
    f.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(LogError, match="UTF-8"):
        logio.read_csv(f)


def test_infinity_is_a_missing_value():
    log = parse("time,speed_kmh\n2027-01-01T10:00:00,inf\n2027-01-01T10:00:01,3\n")
    assert math.isnan(log.speed[0])


def test_clock_drops_empty_milliseconds():
    assert logio.clock(logio.make_log.__globals__["datetime"](2027, 1, 1), 1.0) == "2027-01-01T00:00:01"
    assert logio.clock(logio.make_log.__globals__["datetime"](2027, 1, 1), 1.25) == "2027-01-01T00:00:01.250"
