"""Documentation claims that code can check.

Prose drifts silently. These are the handful of claims where drift would send
an operator to a file that no longer works the way the sentence says.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "sssf"


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
