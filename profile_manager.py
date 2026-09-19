# profile_manager.py
import json
from pathlib import Path

PROFILE_PATH = Path(__file__).parent / "user_profile.json"

DEFAULT_PROFILE = {
    "first_run": True,
    "last_strategy": None,
    "test_history": [],
}


def load_profile():
    if not PROFILE_PATH.exists():
        return dict(DEFAULT_PROFILE)
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_PROFILE.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(DEFAULT_PROFILE)


def save_profile(profile):
    try:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def mark_first_run_done(profile):
    profile["first_run"] = False
    save_profile(profile)


def save_last_strategy(profile, strategy_result, engine_name, mode_name):
    profile["last_strategy"] = {
        "name": strategy_result["name"],
        "engine": engine_name,
        "mode": mode_name,
        "exe": strategy_result["exe"],
        "args": strategy_result["args"],
        "success": strategy_result["success"],
        "total": strategy_result["total"],
    }
    save_profile(profile)


def add_test_history(profile, summary):
    profile.setdefault("test_history", [])
    profile["test_history"].insert(0, summary)
    profile["test_history"] = profile["test_history"][:10]
    save_profile(profile)