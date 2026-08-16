import os
import pytest
from src.config import load_config, FlowJobConfig

def test_load_config_loads_all_sections():
    config = load_config("flowjob.yaml")
    assert isinstance(config, FlowJobConfig)
    assert config.critic.model is not None
    assert config.writer.max_writer_rounds == 3
    assert config.grilling.max_turns_per_gap == 5
    assert config.auditor.max_attempts == 3

def test_flowjob_model_env_override(monkeypatch):
    monkeypatch.setenv("FLOWJOB_MODEL", "custom/test-model")
    config = load_config("flowjob.yaml")
    assert config.critic.model == "custom/test-model"
    assert config.writer.model == "custom/test-model"
    assert config.grilling.model == "custom/test-model"
    assert config.auditor.model == "custom/test-model"
    assert config.analyst.model == "custom/test-model"
    assert config.tailor.model == "custom/test-model"
    assert config.editor.model == "custom/test-model"
