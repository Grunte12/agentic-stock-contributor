import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "stock_analytics.json"
DEFAULT_DATA = ROOT / "data" / "stock_analytics"
LOCAL_CONFIG = ROOT / "config" / "local.json"


def load_config(path=None):
    return json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def load_live_config():
    """The default config with the user's own `config/local.json` (gitignored) laid over it, one section deep, so a
    personal choice such as upload switches stays out of the shipped defaults."""
    cfg = load_config()
    if LOCAL_CONFIG.exists():
        for key, value in json.loads(LOCAL_CONFIG.read_text(encoding="utf-8")).items():
            cfg[key] = {**cfg[key], **value} if isinstance(value, dict) and isinstance(cfg.get(key), dict) else value
    return cfg


def upload_stage_cfg(cfg):
    """The upload_stage section. A config loaded from the default file is re-read on every use, so the user's on/off
    switch takes effect at once, in a running server too. A config passed in (tests) is used as given."""
    return load_live_config()["upload_stage"] if cfg.get("_live_config") else cfg["upload_stage"]


def upload_metadata_cfg(cfg):
    """The upload_metadata section, re-read on every use like upload_stage (the user's on/off switch)."""
    return load_live_config()["upload_metadata"] if cfg.get("_live_config") else cfg["upload_metadata"]


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def metrics_version(cfg):
    """Changing bands, rating rules or top_n changes this value, so old metrics keep their old version."""
    basis = {k: cfg[k] for k in ("bands", "rating", "top_n", "events", "recency", "momentum", "opportunity", "lead", "calibration", "own_keywords")}
    return "1-" + hashlib.sha256(canon(basis).encode()).hexdigest()[:8]
