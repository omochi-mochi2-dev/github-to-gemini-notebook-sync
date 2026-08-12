import yaml
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """
    config.yaml を読み込み、必要な環境変数を検証する。
    """
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config file: {e}")
        raise ValueError(f"Failed to parse config file: {e}")

    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable is not set.")
        raise ValueError("GITHUB_TOKEN environment variable is not set.")
        
    # Inject token into config for ease of use
    config['GITHUB_TOKEN'] = github_token
    return config
