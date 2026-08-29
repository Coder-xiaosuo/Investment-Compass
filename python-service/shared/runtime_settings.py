import copy
import json
import os
import threading
from typing import Optional

from shared.crypto_utils import decrypt_str, encrypt_str

_SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(_SCRIPT_DIR, "config", "settings.json")

SENSITIVE_FIELDS = [
    ("provider", "api_key"),
    ("feishu", "webhook_url"),
    ("feishu", "secret"),
    ("feishu", "app_secret"),
    ("pushplus", "token"),
    ("tushare", "token"),
    ("qwen", "api_key"),
]

_TOP_LEVEL_SECTIONS = ["provider", "general", "feishu", "tushare", "pushplus", "scheduler"]


class RuntimeSettings:
    def __init__(self):
        self._lock = threading.RLock()
        self._version = 0
        self._data = self._read_file()

    def _read_file(self) -> dict:
        if not os.path.exists(SETTINGS_PATH):
            data = {}
            for sec in _TOP_LEVEL_SECTIONS:
                data[sec] = {}
            return data
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        data = {}
        for sec in _TOP_LEVEL_SECTIONS:
            if sec in raw and isinstance(raw[sec], dict):
                data[sec] = copy.deepcopy(raw[sec])
            else:
                data[sec] = {}
        for sec in raw:
            if sec not in data and isinstance(raw[sec], dict):
                data[sec] = copy.deepcopy(raw[sec])
        return data

    def _atomic_write(self, data: dict) -> None:
        tmp_path = SETTINGS_PATH + ".tmp"
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_PATH)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot_dict(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def _is_sensitive(self, section: str, key: str) -> bool:
        return (section, key) in SENSITIVE_FIELDS

    def _deep_merge_section(self, existing: dict, patch: dict, section: str) -> dict:
        result = copy.deepcopy(existing)
        for key, value in patch.items():
            if key not in patch:
                continue
            if self._is_sensitive(section, key):
                if isinstance(value, str) and value != "" and not value.startswith("fenc:"):
                    result[key] = encrypt_str(value)
                elif value == "":
                    result[key] = ""
            else:
                result[key] = copy.deepcopy(value)
        return result

    def update(self, patch: dict) -> tuple:
        with self._lock:
            new_data = copy.deepcopy(self._data)
            for section, section_patch in patch.items():
                if not isinstance(section_patch, dict):
                    continue
                if section in new_data and isinstance(new_data[section], dict):
                    new_data[section] = self._deep_merge_section(
                        new_data[section], section_patch, section
                    )
                else:
                    new_data[section] = self._deep_merge_section(
                        {}, section_patch, section
                    )
            self._data = new_data
            self._atomic_write(new_data)
            self._version += 1
            return self._version, self.snapshot_dict()

    def get_plaintext(self, field_path: str) -> Optional[str]:
        with self._lock:
            parts = field_path.split(".")
            if len(parts) < 2:
                return None
            section = parts[0]
            key = ".".join(parts[1:])
            section_data = self._data.get(section, {})
            if not isinstance(section_data, dict):
                return None
            raw = section_data.get(key)
            if raw is None or raw == "":
                return raw if raw == "" else None
            if isinstance(raw, str) and raw.startswith("fenc:"):
                return decrypt_str(raw)
            return raw if isinstance(raw, str) else str(raw)

    def get_plaintext_api_key(self) -> str:
        val = self.get_plaintext("provider.api_key")
        return val if val is not None else ""

    @property
    def deepseek_model(self) -> str:
        snap = self.snapshot_dict()
        prov = snap.get("provider", {})
        return prov.get("model", "deepseek-v4-flash")

    @property
    def deepseek_base_url(self) -> str:
        snap = self.snapshot_dict()
        prov = snap.get("provider", {})
        return prov.get("base_url", "https://api.deepseek.com")

    @property
    def deepseek_thinking(self) -> bool:
        snap = self.snapshot_dict()
        prov = snap.get("provider", {})
        return prov.get("thinking", True)

    @property
    def deepseek_reasoning_effort(self) -> str:
        snap = self.snapshot_dict()
        prov = snap.get("provider", {})
        return prov.get("reasoning_effort", "high")


runtime_settings = RuntimeSettings()
