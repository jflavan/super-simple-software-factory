"""Documentation claims that code can check.

Prose drifts silently. These are the handful of claims where drift would send
an operator to a file that no longer works the way the sentence says.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "sssf"
COOKBOOKS = SKILL / "cookbooks"


def _text(*parts) -> str:
    return (SKILL.joinpath(*parts)).read_text(encoding="utf-8")


def test_the_install_cookbook_documents_every_flag():
    text = _text("cookbooks", "install.md")
    for flag in ("--profile", "--no-profile", "--doctor", "--force"):
        assert flag in text, flag


def test_the_install_cookbook_explains_how_to_add_a_framework():
    text = _text("cookbooks", "install.md")
    assert "Adding a framework" in text
    for path in ("frameworks/", "gates/", "prompts/", "profile.yaml"):
        assert path in text, path


def test_the_documented_framework_interface_matches_the_code():
    """The doc lists the names a framework must expose; drift here is a trap."""
    import sys
    sys.path.insert(0, str(SKILL / "templates"))
    from profiles import frameworks

    text = _text("cookbooks", "install.md")
    for name in frameworks.FRAMEWORK_INTERFACE:
        assert name in text, name


def test_the_config_reference_documents_doc_policy():
    text = _text("references", "config.md")
    assert "doc_policy" in text
    assert "require" in text


def test_the_config_reference_documents_the_block_tiers():
    text = _text("references", "config.md")
    assert "quality_blocks.py" in text
    assert "tier" in text


def test_no_document_still_tells_operators_to_edit_quality_py_by_hand():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "replace this echo" not in readme
    assert "quality_blocks.py" in readme


def test_the_skill_describes_profiles_and_frameworks():
    text = _text("SKILL.md").lower()
    assert "profile" in text
    assert "framework" in text


def test_no_cookbook_routes_operators_to_wire_a_real_command_in_quality_py():
    """`quality.py` is the engine and never changes; the real commands are
    generated into `quality_blocks.py`. Following the old advice literally in
    a profiled repo edits dead code — `blocks()` returns the generated list
    and never reaches `PLACEHOLDER_BLOCKS`, and `quality.py` is a stamped file
    `--force` overwrites. update_adw.md and create_adw.md both once said this.
    """
    pattern = re.compile(
        r"(?:wire|write|put|add)[^.\n]{0,60}real command[^.\n]{0,60}`quality\.py`",
        re.IGNORECASE)
    offenders = [path.name for path in sorted(COOKBOOKS.glob("*.md"))
                if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == [], offenders


def test_update_modules_and_overview_point_generated_files_at_quality_blocks():
    """`update_modules.md`'s module table and `sssf_overview.md`'s tree both
    list `adw_modules/` - both must describe a profiled install, naming the
    generated `quality_blocks.py`, `profile_gates.py`, and a per-framework
    gate module rather than describing `quality.py` as owning the commands."""
    for name in ("update_modules.md", "sssf_overview.md"):
        text = _text("cookbooks", name)
        assert "quality_blocks.py" in text, name
        assert "profile_gates.py" in text, name
        assert "gates_" in text, name


def test_update_adw_and_create_adw_point_to_quality_blocks_for_real_commands():
    for name in ("update_adw.md", "create_adw.md"):
        text = _text("cookbooks", name)
        assert "quality_blocks.py" in text, name
