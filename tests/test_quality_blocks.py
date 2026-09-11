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
    # Native separators on both sides, no normalization — this pins the
    # resolved workdir, not just a relative fragment of the spec's cwd.
    assert str(tmp_path / "apps" / "nope") in Path(result.output_artifact).read_text()


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
    from pydantic import ValidationError
    for escape in ("/etc", "C:/Windows", "D:\\other"):
        with pytest.raises(ValidationError):
            QualityCheckSpec(name="x", area="backend", operation="build",
                             argv=["true"], cwd=escape)


def test_a_cwd_that_climbs_out_of_the_repo_is_refused():
    from pydantic import ValidationError
    for escape in ("..", "../sibling", "apps/../../elsewhere"):
        with pytest.raises(ValidationError):
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


@pytest.fixture
def generated_package(tmp_path, monkeypatch):
    """A throwaway copy of adw_modules whose quality_blocks.py we control.

    Call it with the source to write, or with None for "no generated file".

    sys.modules is snapshotted and fully restored, dropping anything the import
    added. monkeypatch.delitem restores only what it DELETED, and
    `adw_modules.quality_blocks` is never in sys.modules to begin with — so
    without this it survives the test, and find_spec consults sys.modules
    before the filesystem. The leaked module carries a different
    QualityCheckSpec class object, built from the shadowed data_types, so the
    next test that exercises the real loader fails validation by file order.
    """
    import importlib
    import shutil
    import sys

    before = {name: module for name, module in sys.modules.items()
              if name == "adw_modules" or name.startswith("adw_modules.")}

    def build(source: str | None):
        package = tmp_path / "adw_modules"
        if not package.exists():
            shutil.copytree(Path(quality.__file__).parent, package,
                            ignore=shutil.ignore_patterns("__pycache__"))
        generated = package / "quality_blocks.py"
        if source is None:
            generated.unlink(missing_ok=True)
        else:
            generated.write_text(source, encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        for name in list(sys.modules):
            if name == "adw_modules" or name.startswith("adw_modules."):
                del sys.modules[name]
        return importlib.import_module("adw_modules.quality")

    yield build

    for name in list(sys.modules):
        if name == "adw_modules" or name.startswith("adw_modules."):
            del sys.modules[name]
    sys.modules.update(before)


def test_a_real_generated_file_is_loaded(generated_package):
    module = generated_package(
        "from .data_types import QualityCheckSpec\n"
        "BLOCKS = [QualityCheckSpec(name='t', area='backend',\n"
        "                           operation='test', argv=['echo', 'x'])]\n")
    assert [b.name for b in module.blocks()] == ["t"]


def test_no_generated_file_falls_back_to_placeholders(generated_package):
    module = generated_package(None)
    assert [b.name for b in module.blocks()] == ["test", "lint", "typecheck", "build"]


def test_a_syntax_error_in_the_generated_file_is_fatal(generated_package):
    module = generated_package("BLOCKS = [\n")
    with pytest.raises(SyntaxError):
        module.blocks()


def test_a_generated_file_without_BLOCKS_is_fatal(generated_package):
    module = generated_package("SPECS = []\n")
    with pytest.raises(ImportError):
        module.blocks()


def test_a_missing_dependency_named_like_the_module_is_still_fatal(generated_package):
    """The hole find_spec closes: a self-named missing import must not look absent."""
    module = generated_package("import quality_blocks\nBLOCKS = []\n")
    with pytest.raises(ModuleNotFoundError):
        module.blocks()


def test_a_generated_file_emitting_dicts_fails_at_the_boundary(generated_package):
    """Not later, inside _run_tier, with an AttributeError far from the cause."""
    from pydantic import ValidationError
    module = generated_package("BLOCKS = [{'name': 'a'}]\n")
    with pytest.raises(ValidationError):
        module.blocks()


def test_duplicate_block_names_are_refused(monkeypatch):
    """A block's name is its artifact directory; two of one name lose evidence."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="test", area="backend", operation="test", argv=["a"]),
        QualityCheckSpec(name="test", area="frontend", operation="test", argv=["b"]),
    ])
    with pytest.raises(ValueError, match="duplicate quality block name"):
        quality.blocks()


def test_duplicate_block_names_are_refused_case_insensitively(monkeypatch):
    """A block's name is its artifact directory, and Windows and default macOS
    filesystems are case-insensitive - `test-Web` and `test-web` collide on
    disk even though the strings differ."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="test-Web", area="backend", operation="test", argv=["a"]),
        QualityCheckSpec(name="test-web", area="frontend", operation="test", argv=["b"]),
    ])
    with pytest.raises(ValueError, match="duplicate quality block name"):
        quality.blocks()


def test_an_empty_block_list_refuses_to_report_green(tmp_path, monkeypatch):
    """Zero commands is not success. It is the failure this design removes."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [])
    with pytest.raises(RuntimeError, match="no quality blocks"):
        quality.run_tests(_fake_run(tmp_path))


def test_a_fast_tier_with_nothing_in_it_refuses_to_report_green(tmp_path, monkeypatch):
    """A repo whose only suite needs Docker must not silently skip its fix loop."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="integration", area="backend", operation="test",
                         argv=["a"], tier="full"),
    ])
    with pytest.raises(RuntimeError, match="none selected"):
        quality.run_tests(_fake_run(tmp_path))
    # ...but run_quality, which selects both tiers, is fine
    monkeypatch.setattr(quality, "_run", lambda spec, run: _passing(spec, []))
    assert quality.run_quality(_fake_run(tmp_path)).passed


def test_a_test_block_is_traced_as_a_test(tmp_path, monkeypatch):
    """Not as a build. A trace query for test failures has to find them."""
    events = []
    run = _fake_run(tmp_path)
    run.tracer = SimpleNamespace(event=events.append)
    monkeypatch.setattr(quality.subprocess, "run", lambda argv, **kw: SimpleNamespace(
        returncode=0, stdout="", stderr=""))

    quality._run(QualityCheckSpec(name="test-api", area="backend", operation="test",
                                  argv=["git", "status"]), run)

    assert events[0].payload["operation"] == "test"


def test_a_generated_block_runs_end_to_end(tmp_path, generated_package):
    """blocks() -> _run_tier -> _run, with a real subprocess and a real artifact."""
    module = generated_package(
        "from .data_types import QualityCheckSpec\n"
        "import sys\n"
        "BLOCKS = [QualityCheckSpec(name='hello', area='backend',\n"
        "                           operation='test',\n"
        "                           argv=[sys.executable, '-c',\n"
        "                                 \"print('ran')\"])]\n")
    work = tmp_path / "work"
    work.mkdir()

    result = module.run_tests(_fake_run(work))

    assert result.passed
    assert len(result.checks) == 1
    assert "ran" in Path(result.artifacts[0]).read_text()
