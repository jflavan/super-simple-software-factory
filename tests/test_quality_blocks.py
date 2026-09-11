"""Quality blocks are data: a tier, a working directory, and an argv."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from adw_modules import quality
from adw_modules.data_types import QualityCheckResult, QualityCheckSpec


def _fake_run(tmp_path):
    """The smallest stand-in quality._run actually touches.

    Mirrors the helper in tests/test_quality_launch.py — it reads run.adw_id,
    run.repo_root, run.context_handoff_dir, run.phases[-1], run.tracer.event
    and run.console.note, and nothing else.
    """
    return SimpleNamespace(
        adw_id="testadw",
        repo_root=tmp_path,
        context_handoff_dir=tmp_path,
        phases=[SimpleNamespace(seq=1, phase_id="testadw_01_probe")],
        tracer=SimpleNamespace(event=lambda record: None),
        console=SimpleNamespace(note=lambda message: None),
    )


def _passing(spec, ran):
    ran.append(spec.name)
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=0, passed=True,
                              duration_seconds=0.0, output_artifact="/dev/null")


def _failing(spec):
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=1, passed=False,
                              duration_seconds=0.0, output_artifact="/dev/null",
                              output_tail="boom")


def test_spec_defaults_to_the_fast_tier_at_the_repo_root():
    spec = QualityCheckSpec(name="x", area="backend", operation="build", argv=["true"])
    assert spec.tier == "fast"
    assert spec.cwd == "."


def test_spec_rejects_an_unknown_tier():
    with pytest.raises(Exception):
        QualityCheckSpec(name="x", area="backend", operation="build",
                         argv=["true"], tier="someday")


def test_run_launches_the_block_in_its_own_cwd(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)
    (tmp_path / "apps" / "web").mkdir(parents=True)

    quality._run(QualityCheckSpec(
        name="check-web", area="frontend", operation="typecheck",
        argv=["git", "status"], cwd="apps/web",
    ), _fake_run(tmp_path))

    assert Path(captured["cwd"]) == tmp_path / "apps" / "web"


def test_run_at_the_repo_root_does_not_append_a_dot_segment(tmp_path, monkeypatch):
    """`cwd="."` must resolve to the repo root itself, not `<root>/.`."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    quality._run(QualityCheckSpec(
        name="probe", area="backend", operation="lint", argv=["git", "status"],
    ), _fake_run(tmp_path))

    assert Path(captured["cwd"]) == tmp_path
