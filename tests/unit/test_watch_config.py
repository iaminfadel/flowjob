import pytest
from pydantic import ValidationError
from src.config import WatchConfig, FlowJobConfig
from src.pipeline.watch_lock import acquire_watch_lock, WatchLockHeldError

def test_watch_config_defaults():
    cfg = WatchConfig()
    assert cfg.min_wait_minutes == 45
    assert cfg.max_wait_minutes == 90

def test_watch_config_loads_from_yaml_dict():
    cfg = FlowJobConfig(watch={"min_wait_minutes": 10, "max_wait_minutes": 20})
    assert cfg.watch.min_wait_minutes == 10
    assert cfg.watch.max_wait_minutes == 20

def test_watch_config_defaults_in_flowjob_config():
    cfg = FlowJobConfig()
    assert cfg.watch.min_wait_minutes == 45
    assert cfg.watch.max_wait_minutes == 90

def test_watch_config_rejects_min_ge_max():
    with pytest.raises(ValidationError):
        WatchConfig(min_wait_minutes=90, max_wait_minutes=45)
    with pytest.raises(ValidationError):
        WatchConfig(min_wait_minutes=30, max_wait_minutes=30)

def test_watch_config_rejects_non_positive():
    with pytest.raises(ValidationError):
        WatchConfig(min_wait_minutes=0, max_wait_minutes=90)

def test_lockfile_exclusive(tmp_path):
    lock_path = tmp_path / "watch.lock"
    with acquire_watch_lock(lock_path):
        with pytest.raises(WatchLockHeldError):
            with acquire_watch_lock(lock_path):
                pass

def test_lockfile_released_after_context(tmp_path):
    lock_path = tmp_path / "watch.lock"
    with acquire_watch_lock(lock_path):
        pass
    with acquire_watch_lock(lock_path):
        pass
