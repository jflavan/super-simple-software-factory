"""Quality blocks are data: a tier, a working directory, and an argv."""

import sys
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


def test_run_at_the_repo_root_launches_at_the_repo_root(tmp_path, monkeypatch):
    """The default `cwd="."` must resolve to the repo root itself."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    quality._run(QualityCheckSpec(
        name="probe", area="backend", operation="lint", argv=["git", "status"],
    ), _fake_run(tmp_path))

    assert Path(captured["cwd"]) == tmp_path


def test_a_block_really_lands_in_its_package_directory(tmp_path):
    """No monkeypatch: prove the process MOVED, not that we passed a value."""
    (tmp_path / "apps" / "web").mkdir(parents=True)

    result = quality._run(QualityCheckSpec(
        name="w", area="frontend", operation="typecheck",
        argv=[sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd="apps/web",
    ), _fake_run(tmp_path))

    assert result.returncode == 0
    assert Path(result.output_tail.strip()) == tmp_path / "apps" / "web"


def test_a_missing_working_directory_is_named_in_the_artifact(tmp_path):
    """Otherwise this reads as exit 127 'missing binary' on Windows."""
    result = quality._run(QualityCheckSpec(
        name="gone", area="frontend", operation="build",
        argv=[sys.executable, "-c", "pass"], cwd="apps/nope",
    ), _fake_run(tmp_path))

    assert not result.passed
    # Compare with slashes normalized: the artifact renders the cwd with the
    # platform's native separator (backslashes on Windows), and the point of
    # this test is that the missing directory is named at all, not which
    # separator character names it.
    assert "apps/nope" in Path(result.output_artifact).read_text().replace("\\", "/")


def test_the_trace_payload_carries_the_cwd_and_the_tier(tmp_path, monkeypatch):
    events = []
    run = _fake_run(tmp_path)
    run.tracer = SimpleNamespace(event=events.append)
    monkeypatch.setattr(quality.subprocess, "run", lambda argv, **kw: SimpleNamespace(
        returncode=0, stdout="", stderr=""))

    quality._run(QualityCheckSpec(
        name="check-web", area="frontend", operation="typecheck",
        argv=["git", "status"], cwd="apps/web", tier="full",
    ), run)

    assert events[0].payload["cwd"] == "apps/web"
    assert events[0].payload["tier"] == "full"


def test_an_absolute_cwd_is_refused(tmp_path):
    """`Path(root) / "/elsewhere"` discards the root and succeeds in the wrong place."""
    for escape in ("/etc", "C:/Windows", "D:\\other"):
        with pytest.raises(Exception):
            QualityCheckSpec(name="x", area="backend", operation="build",
                             argv=["true"], cwd=escape)


def test_windows_separators_in_cwd_are_folded(tmp_path):
    spec = QualityCheckSpec(name="x", area="backend", operation="build",
                            argv=["true"], cwd="apps\\web")
    assert spec.cwd == "apps/web"


def test_placeholder_blocks_are_used_when_nothing_was_generated(monkeypatch):
    """An un-profiled install must still announce that it is fake."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: None)
    names = [b.name for b in quality.blocks()]
    assert names == ["test", "lint", "typecheck", "build"]
    assert all("PLACEHOLDER" in " ".join(b.argv) for b in quality.blocks())


def test_generated_blocks_replace_the_placeholders(monkeypatch):
    generated = [QualityCheckSpec(name="test-api", area="backend", operation="build",
                                  argv=["just", "test-api"], tier="fast")]
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: generated)
    assert [b.name for b in quality.blocks()] == ["test-api"]


def test_run_tests_runs_the_fast_tier_only(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build",
                         argv=["a"], tier="fast"),
        QualityCheckSpec(name="integration", area="backend", operation="build",
                         argv=["b"], tier="full"),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _passing(spec, ran))

    result = quality.run_tests(_fake_run(tmp_path))

    assert ran == ["unit"]
    assert result.passed


def test_run_quality_runs_every_tier(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build",
                         argv=["a"], tier="fast"),
        QualityCheckSpec(name="integration", area="backend", operation="build",
                         argv=["b"], tier="full"),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _passing(spec, ran))

    quality.run_quality(_fake_run(tmp_path))

    assert ran == ["unit", "integration"]


def test_a_failing_block_is_reported_with_its_output(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build", argv=["a"]),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _failing(spec))

    result = quality.run_tests(_fake_run(tmp_path))

    assert not result.passed
    assert len(result.failures) == 1
    assert "exited 1" in result.failures[0]
    assert "boom" in result.failures[0]


def test_a_broken_generated_module_is_not_swallowed(monkeypatch):
    """A typo in quality_blocks.py must raise, not silently fall back to fakes."""
    def raise_unrelated():
        raise ModuleNotFoundError("No module named 'nonexistent_dependency'",
                                  name="nonexistent_dependency")

    monkeypatch.setattr(quality, "_import_generated_blocks", raise_unrelated)
    with pytest.raises(ModuleNotFoundError):
        quality.blocks()
