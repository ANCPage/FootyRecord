"""Config must not be readable two ways with different answers.

18 call sites read `config.config.data_dir`, 26 read `config.DATA_DIR`. Before
this, a runtime override changed one and not the other, which produced a real
error in a run (`AttributeError: module 'Core.config' has no attribute 'data_dir'`)
and, worse, could have silently pointed a script at a different data folder
(audit 2026-09-14, finding 6).
"""
from Core import config


def test_setting_the_object_moves_the_constant():
    original = config.DATA_DIR
    try:
        config.config.data_dir = '/tmp/some-other-place'
        assert config.DATA_DIR == '/tmp/some-other-place'
        assert config.config.data_dir == config.DATA_DIR
    finally:
        config.config.data_dir = original


def test_the_other_mirrors_agree_too():
    original = config.config.window_size
    try:
        config.config.window_size = 42
        assert config.WINDOW_SIZE == 42
    finally:
        config.config.window_size = original
        assert config.WINDOW_SIZE == original


def test_validation_still_rejects_nonsense():
    import pytest
    with pytest.raises(ValueError):
        config.config.decay_factor = 5.0
