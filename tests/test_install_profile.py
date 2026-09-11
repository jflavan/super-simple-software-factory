"""install.py --profile: stamp a factory that is wired to this repo."""

import subprocess
import sys
from pathlib import Path

from profile_fixtures import CSPROJ_APP, dotnet_svelte_repo, package, sln, write

INSTALL = (Path(__file__).resolve().parent.parent
           / ".claude" / "skills" / "sssf" / "scripts" / "install.py")


def _install(cwd, *args):
    return subprocess.run([sys.executable, str(INSTALL), *args],
                          cwd=cwd, capture_output=True, text=True)


def _generated(root):
    modules = root / "adws" / "adw_modules"
    return {
        "blocks": modules / "quality_blocks.py",
        "gates": modules / "profile_gates.py",
        "dotnet_gates": modules / "gates_dotnet.py",
        "sveltekit_gates": modules / "gates_sveltekit.py",
        "overlay": root / "adws" / "adw_data" / "prompt_engineering" / "profile_overlay.md",
    }


def test_a_matching_repo_is_profiled_automatically(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "dotnet-svelte" in result.stdout
    for path in _generated(tmp_path).values():
        assert path.is_file(), path


def test_the_generated_blocks_name_this_repo_s_real_commands(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    text = _generated(tmp_path)["blocks"].read_text()
    assert "dotnet" in text
    assert "PLACEHOLDER" not in text


def test_a_gate_module_is_stamped_per_declared_framework(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    assert "ef_migration_triad" in _generated(tmp_path)["dotnet_gates"].read_text()
    assert "sveltekit_csp" in _generated(tmp_path)["sveltekit_gates"].read_text()


def test_no_profile_leaves_the_factory_unwired(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--no-profile")
    assert result.returncode == 0, result.stderr
    for path in _generated(tmp_path).values():
        assert not path.exists(), path
    assert (tmp_path / "adws" / "adw_modules" / "quality.py").is_file()


def test_an_unrecognised_repo_installs_without_a_profile(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no profile" in result.stdout.lower()
    assert (tmp_path / "adws" / "adw_modules" / "quality.py").is_file()
    assert not _generated(tmp_path)["blocks"].exists()


def test_an_unknown_profile_name_fails_and_lists_the_real_ones(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--profile", "cobol-jquery")
    assert result.returncode != 0
    assert "dotnet-svelte" in result.stdout + result.stderr


def test_profile_and_no_profile_together_is_refused(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert _install(tmp_path, "--profile", "dotnet-svelte", "--no-profile").returncode != 0


def test_the_report_names_what_it_could_not_resolve(tmp_path):
    """A repo with no test project must say so at install time."""
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    package(tmp_path, "web", {"build": "vite build"})
    result = _install(tmp_path)
    assert "unresolved" in result.stdout.lower()
    assert "unit-tests" in result.stdout


def test_the_report_lists_the_blocks_with_their_tiers(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path)
    assert "fast" in result.stdout
    assert "full" in result.stdout
    assert "build-sln" in result.stdout


def test_every_line_of_output_is_ascii(tmp_path):
    """The console this prints to may be cp1252; a crash here kills the install."""
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path).stdout.encode("ascii")


def test_installing_twice_is_idempotent(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    first = _generated(tmp_path)["blocks"].read_text()
    assert _install(tmp_path).returncode == 0
    second = _generated(tmp_path)["blocks"].read_text()
    # the generated file is rewritten from facts, so its blocks are identical
    assert first.split("BLOCKS = [")[1] == second.split("BLOCKS = [")[1]
