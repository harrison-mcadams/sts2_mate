"""
Configuration management for STS2 Companion.
Handles persistent settings (API keys, AI model selection) via environment variables
and local JSON config file.
"""

import json
import os
from typing import Any, Dict, Optional

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CONFIG_FILE = os.path.join(CONFIG_DIR, "companion_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_key": "",
    "gemini_model": "gemini-3.8-flash",
    "enable_search_grounding": True,
}


def load_config() -> Dict[str, Any]:
    """Loads configuration from file with defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Saves updated configuration to file."""
    cfg = load_config()
    cfg.update(updates)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Failed to save config: {e}")
    return cfg


def get_gemini_api_key() -> Optional[str]:
    """
    Returns effective Gemini API key.
    Precedence:
    1. GEMINI_API_KEY environment variable
    2. GOOGLE_API_KEY environment variable
    3. companion_config.json
    """
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    cfg = load_config()
    file_key = cfg.get("gemini_api_key", "").strip()
    return file_key if file_key else None


def get_gemini_model() -> str:
    """Returns selected Gemini model name."""
    cfg = load_config()
    return cfg.get("gemini_model", DEFAULT_CONFIG["gemini_model"]) or DEFAULT_CONFIG["gemini_model"]
