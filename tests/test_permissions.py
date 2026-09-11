"""What an agent may change, pinned.

permissions.permitted() is the function that stops an agent rewriting the
machinery that grades it. It had no tests until this file, and Task 3 moved its
glob engine into utils, so these pin the behaviour that move had to preserve.
"""

from adw_modules import permissions
from adw_modules.data_types import AgentConfig, ConfigDefaults, PromptEngineering, SSSFConfig


def _cfg(**defaults) -> SSSFConfig:
    return SSSFConfig(defaults=ConfigDefaults(**defaults))


def _agent(**kwargs) -> AgentConfig:
    kwargs.setdefault("name", "builder")
    kwargs.setdefault("prompt_engineering",
                      PromptEngineering(system="s.md", user="u.md"))
    return AgentConfig(**kwargs)


# ── permitted() ──────────────────────────────────────────────────────────────

def test_the_session_runtime_is_always_writable_even_for_a_read_only_agent():
    """A read-only agent can still write its own report."""
    cfg = _cfg()
    agent = _agent(writes=[])
    assert permissions.permitted("adws/adw_data/sessions/x/report.md", agent, cfg)


def test_writes_none_is_unrestricted_for_an_ordinary_path():
    cfg = _cfg()
    agent = _agent(writes=None)
    assert permissions.permitted("src/main.py", agent, cfg)


def test_writes_empty_list_is_read_only_with_respect_to_the_repo():
    cfg = _cfg()
    agent = _agent(writes=[])
    assert not permissions.permitted("src/main.py", agent, cfg)


def test_writes_with_a_directory_prefix_permits_inside_and_refuses_outside():
    cfg = _cfg()
    agent = _agent(writes=["specs/"])
    assert permissions.permitted("specs/plan.md", agent, cfg)
    assert not permissions.permitted("src/main.py", agent, cfg)


def test_protected_files_refuses_an_otherwise_unrestricted_agent():
    cfg = _cfg()
    agent = _agent(writes=None)
    assert not permissions.permitted("adws/adw_modules/quality.py", agent, cfg)
    assert not permissions.permitted("adws/adw_sssf_config/sssf.config.yaml", agent, cfg)
    assert not permissions.permitted("adws/adw_plan.py", agent, cfg)


def test_naming_a_protected_path_in_writes_unlocks_it():
    """Documented precedence: an agent's own writes list beats protected_files."""
    cfg = _cfg()
    agent = _agent(writes=["adws/adw_modules/quality.py"])
    assert permissions.permitted("adws/adw_modules/quality.py", agent, cfg)


def test_adw_star_py_does_not_reach_into_adw_data():
    """The `*`-stops-at-`/` property: adws/adw_*.py must not match adws/adw_data/...

    data_dir is moved elsewhere so always_writable's own grant for the
    session runtime cannot mask what protected_files alone decides here.
    """
    cfg = _cfg(data_dir="var/session_data")
    agent = _agent(writes=None)
    assert permissions.permitted(
        "adws/adw_data/sessions/x/adw_y.py", agent, cfg)


def test_a_backslash_in_protected_files_still_protects():
    """The Fix 1 regression: before the pattern fold, this returned True."""
    cfg = _cfg(protected_files=["adws\\adw_modules\\"])
    agent = _agent(writes=None)
    assert not permissions.permitted("adws/adw_modules/quality.py", agent, cfg)


# ── changed_paths() ──────────────────────────────────────────────────────────

def test_changed_paths_reports_an_appeared_path():
    before = {}
    after = {"new.txt": "untracked"}
    assert permissions.changed_paths(before, after) == ["new.txt"]


def test_changed_paths_reports_a_vanished_path():
    before = {"gone.txt": "1,0"}
    after = {}
    assert permissions.changed_paths(before, after) == ["gone.txt"]


def test_changed_paths_reports_a_path_whose_fingerprint_changed():
    before = {"a.py": "1,0"}
    after = {"a.py": "2,1"}
    assert permissions.changed_paths(before, after) == ["a.py"]


def test_changed_paths_omits_a_path_identical_in_both_snapshots():
    before = {"a.py": "1,0", "b.py": "3,0"}
    after = {"a.py": "1,0", "b.py": "4,0"}
    assert permissions.changed_paths(before, after) == ["b.py"]
