import yaml
from typing import Dict, Any

def load_config(path: str) -> Dict[str, Any]:
    """
    Load a YAML configuration file and return it as a dictionary.

    Args:
        path (str): The path to the YAML file.

    Returns:
        Dict[str, Any]: The loaded configuration.
    """
    with open(path, 'r') as f:
        return yaml.safe_load(f)
