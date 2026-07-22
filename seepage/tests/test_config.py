import os
from src.core.config import load_config

def test_load_config():
    config_path = os.path.join(os.path.dirname(__file__), "..", "configs", "intersection_default.yaml")
    config = load_config(config_path)
    
    assert "modes" in config
    assert len(config["modes"]) == 4
    assert config["modes"] == ["two_wheeler", "three_wheeler", "car", "bus"]
