"""A quality block launches a resolved argv but records the bare one."""

from pathlib import Path
from types import SimpleNamespace

from adw_modules import quality
from adw_modules.data_types import QualityCheckSpec


def _fake_run(tmp_path):
    """The smallest stand-in quality._run actually touches.

    It reads run.adw_id, run.repo_root, run.context_handoff_dir,
    run.phases[-1], run.tracer.event and run.console.note — and nothing else.
    """
    return SimpleNamespace(
        adw_id="testadw",
        repo_root=tmp_path,
        context_handoff_dir=tmp_path,
        phases=[SimpleNamespace(seq=1, phase_id="testadw_01_probe")],
        tracer=SimpleNamespace(event=lambda record: None),
        console=SimpleNamespace(note=lambda message: None),
    )


def test_run_resolves_argv_but_records_the_bare_command(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    result = quality._run(QualityCheckSpec(
        name="probe", area="backend", operation="lint", argv=["git", "status"],
    ), _fake_run(tmp_path))

    # Executed with a resolved absolute path...
    assert captured["argv"][0] != "git"
    assert Path(captured["argv"][0]).is_absolute()
    # ...but the trace keeps the machine-independent form.
    assert result.command == "git status"
