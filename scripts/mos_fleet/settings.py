"""mos-fleet's settings: defaults.toml (next to this file), then
/etc/mos-fleet/config.toml (the computer's), then, for the admin commands,
~/.config/mos-fleet/config.toml (yours). Later files override earlier ones,
key by key."""

import os
import tomllib

DEFAULTS = os.path.join(os.path.dirname(__file__), "defaults.toml")
SYSTEM = "/etc/mos-fleet/config.toml"
USER = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "mos-fleet", "config.toml")


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(user=False):
    conf = {}
    for path in (DEFAULTS, SYSTEM) + ((USER,) if user else ()):
        try:
            with open(path, "rb") as fh:
                conf = merge(conf, tomllib.load(fh))
        except FileNotFoundError:
            pass
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise SystemExit(f"mos-fleet: {path}: {e}")
    return conf


_cache = {}


def get(section, user=False):
    if user not in _cache:
        _cache[user] = load(user)
    return _cache[user].get(section, {})
