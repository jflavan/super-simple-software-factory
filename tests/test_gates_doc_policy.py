"""doc_policy: a change here requires a doc there, declared in YAML."""

from types import SimpleNamespace

import pytest

from adw_modules import gates
from adw_modules.data_types import BuildOutput, DocPolicyRule, SSSFConfig
from adw_modules.utils import changed_files, path_matches, repo_relative


def _run(tmp_path, rules=()):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SSSFConfig(doc_policy=list(rules)))


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


# ── the shared path helpers ──────────────────────────────────────────────────

def test_a_star_does_not_cross_a_directory_separator():
    assert path_matches("adws/adw_plan.py", "adws/adw_*.py")
    assert not path_matches("adws/adw_data/x/adw_y.py", "adws/adw_*.py")


def test_double_star_slash_matches_zero_directories():
    assert path_matches("README.md", "**/*.md")
    assert path_matches("docs/a/b.md", "**/*.md")


def test_a_trailing_slash_is_a_directory_prefix():
    assert path_matches("docs/deep/file.md", "docs/")
    assert not path_matches("documents/file.md", "docs/")


def test_windows_separators_are_normalised():
    assert path_matches("docs\\a.md", "docs/*.md")


def test_repo_relative_strips_an_absolute_root():
    assert repo_relative("/repo/apps/a.cs", "/repo") == "apps/a.cs"
    assert repo_relative("./apps/a.cs", "/repo") == "apps/a.cs"
    assert repo_relative("apps/a.cs", "/repo") == "apps/a.cs"


def test_changed_files_normalises_every_entry(tmp_path):
    envelope = _envelope([str(tmp_path / "a.cs"), "./b.cs", "c\\d.cs"])
    assert changed_files(envelope, _run(tmp_path)) == ["a.cs", "b.cs", "c/d.cs"]


def test_changed_files_on_an_envelope_without_the_field_is_empty(tmp_path):
    assert changed_files(SimpleNamespace(), _run(tmp_path)) == []


# ── the gate ─────────────────────────────────────────────────────────────────

def test_no_rules_means_no_checks(tmp_path):
    report = gates.doc_policy(_envelope(["src/a.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_rule_that_does_not_trigger_records_nothing(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(_envelope(["apps/web/src/page.svelte"]),
                              _run(tmp_path, rules))
    assert report.passed
    assert report.checks == []


def test_a_triggered_rule_demands_its_document(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(_envelope(["apps/api/Identity/AuthService.cs"]),
                              _run(tmp_path, rules))
    assert not report.passed
    assert "docs/AUTH.md" in report.violations[0]
    assert "AuthService.cs" in report.violations[0]


def test_a_triggered_rule_passes_when_the_document_is_in_the_change(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(
        _envelope(["apps/api/Identity/AuthService.cs", "docs/AUTH.md"]),
        _run(tmp_path, rules))
    assert report.passed
    assert len(report.checks) == 1


def test_every_required_document_is_checked_separately(tmp_path):
    rules = [DocPolicyRule(when="apps/web/src/**",
                           require=["docs/ARCHITECTURE.md", "docs/FEATURES.md"])]
    report = gates.doc_policy(
        _envelope(["apps/web/src/routes/+page.svelte", "docs/FEATURES.md"]),
        _run(tmp_path, rules))
    assert len(report.checks) == 2
    assert len(report.violations) == 1
    assert "ARCHITECTURE" in report.violations[0]


def test_a_requirement_may_itself_be_a_glob(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**", require=["docs/*.md"])]
    report = gates.doc_policy(
        _envelope(["apps/api/Program.cs", "docs/anything.md"]),
        _run(tmp_path, rules))
    assert report.passed


def test_absolute_changed_file_paths_are_made_repo_relative(tmp_path):
    """Agents report whatever shape they like; the rule is written repo-relative."""
    rules = [DocPolicyRule(when="apps/api/**", require=["docs/AUTH.md"])]
    absolute = str(tmp_path / "apps" / "api" / "Program.cs")
    report = gates.doc_policy(_envelope([absolute]), _run(tmp_path, rules))
    assert not report.passed


def test_the_config_accepts_a_doc_policy_block(tmp_path):
    import yaml
    from adw_modules import agents
    path = tmp_path / "sssf.config.yaml"
    path.write_text(yaml.safe_dump({
        "defaults": {"coding_agent": "pi"},
        "doc_policy": [{"when": "apps/api/**", "require": ["docs/AUTH.md"]}],
        "agents": [],
    }))
    cfg = agents.load_config(str(path))
    assert cfg.doc_policy[0].when == "apps/api/**"
    assert cfg.doc_policy[0].require == ["docs/AUTH.md"]


def test_doc_policy_defaults_to_empty():
    assert SSSFConfig().doc_policy == []
