from __future__ import annotations

import json

import pytest

from vehicletelemetry import cli


def run(capsys, *args):
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_generate_validate_analyze_with_truth(tmp_path, capsys):
    csv, truth = tmp_path / "d.csv", tmp_path / "t.json"
    code, out, _ = run(capsys, "generate", "-o", str(csv), "--truth", str(truth), "--days", "3", "--seed", "4")
    assert code == 0 and "written:" in out and csv.exists() and truth.exists()
    code, out, _ = run(capsys, "validate", str(csv))
    assert code == 0 and out.startswith("ok: ") and "channels: speed, rpm" in out
    code, out, _ = run(capsys, "analyze", str(csv), "--truth", str(truth), "--out", str(tmp_path / "o"))
    assert code == 0 and "against the truth" in out and "false alarms" in out
    rep = json.loads((tmp_path / "o" / "report.json").read_text())
    assert rep["kind"] == "report" and rep["accuracy"] is not None and rep["source"] == str(csv)
    assert (tmp_path / "o" / "report.md").read_text().startswith("# Vehicle telemetry: ")
    assert (tmp_path / "o" / "summary.png").read_bytes()[1:4] == b"PNG"
    # the same file again, without the truth
    code, out, _ = run(capsys, "analyze", str(csv))
    assert code == 0 and "against the truth" not in out


def test_generate_refuses_to_overwrite_and_can_be_clean(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text("x")
    code, _, err = run(capsys, "generate", "-o", str(f))
    assert code == 2 and "already exists" in err
    code, _out, _ = run(
        capsys, "generate", "-o", str(tmp_path / "c.csv"), "--truth", str(tmp_path / "c.json"), "--days", "2", "--clean"
    )
    assert code == 0
    assert all(not v for v in json.loads((tmp_path / "c.json").read_text())["anomalies"].values())


def test_demo_analysis_and_parameter_flags(capsys):
    code, out, _ = run(capsys, "analyze")
    assert code == 0 and out.startswith("demo drive log (synthetic, 14 days, seed 1): ")
    code, strict, _ = run(capsys, "analyze", "--accel-ms2", "1.2", "--brake-ms2", "1.2")
    harsh = lambda text: int(text.splitlines()[1].split()[2])  # noqa: E731
    assert harsh(strict) > harsh(out)


def test_errors_are_exit_code_2(tmp_path, capsys):
    assert run(capsys, "validate", str(tmp_path / "nope.csv"))[0] == 2
    assert run(capsys, "analyze", "--truth", "t.json")[0] == 2
    bad = tmp_path / "t.json"
    bad.write_text("{not json")
    f = tmp_path / "d.csv"
    f.write_text("time,speed_kmh\n2027-01-01T10:00:00,1\n2027-01-01T10:00:01,2\n")
    code, _, err = run(capsys, "analyze", str(f), "--truth", str(bad))
    assert code == 2 and "truth file" in err
    code, _, err = run(capsys, "analyze", "--gap-s", "5", "--max-fill-s", "9")
    assert code == 2 and "max_fill_s" in err
    code, _, err = run(capsys, "analyze", "--gap-s", "-1")
    assert code == 2
    assert run(capsys, "bench", "--sizes", "5")[0] == 2
    with pytest.raises(SystemExit):
        run(capsys, "nope")


def test_verify_and_bench_and_render(tmp_path, capsys):
    code, out, _ = run(capsys, "verify", "--draws", "3")
    assert code == 0 and "4 of 4 comparisons agree with the literal implementation" in out
    b = tmp_path / "b"
    code, out, _ = run(
        capsys,
        "bench",
        "--sizes",
        "2_000,5000",
        "--repeat",
        "1",
        "--draws",
        "2",
        "--ref-samples",
        "2000",
        "--out",
        str(b),
    )
    assert code == 0 and "written:" in out
    data = json.loads((b / "bench.json").read_text())
    assert data["verification"]["ok"] and [r["samples"] for r in data["analysis"]] == [2000, 5000]
    code, out, _ = run(
        capsys, "render", str(b / "bench.json"), "-o", str(tmp_path / "again.md"), "--figure", str(tmp_path / "f.png")
    )
    assert code == 0 and (tmp_path / "again.md").read_text() == (b / "bench.md").read_text()
    code, out, _ = run(capsys, "render", str(b / "bench.json"))
    assert out.startswith("# Benchmark")


def test_render_rejects_other_files(tmp_path, capsys):
    f = tmp_path / "x.json"
    f.write_text('{"kind": "other"}')
    assert run(capsys, "render", str(f))[0] == 2
    assert run(capsys, "render", str(tmp_path / "missing.json"))[0] == 2


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("vtel ")
