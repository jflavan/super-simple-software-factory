"""The harness itself: adw_modules must be importable from the skill templates."""


def test_adw_modules_is_importable():
    from adw_modules import utils

    assert callable(utils.now_iso)


def test_data_types_is_importable():
    from adw_modules import data_types

    assert data_types.EnvelopeBase is not None


def test_agent_types_are_backend_neutral():
    from adw_modules import data_types

    assert hasattr(data_types, "AgentRequest")
    assert hasattr(data_types, "AgentResult")
    assert not hasattr(data_types, "PiRequest"), "the pi-named alias must be gone"
    assert not hasattr(data_types, "PiResult"), "the pi-named alias must be gone"
