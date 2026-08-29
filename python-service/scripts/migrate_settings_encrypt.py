#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(sys.path[0]).resolve()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.crypto_utils import encrypt_str

SENSITIVE_FIELDS = [
    ("provider", "api_key"),
    ("feishu", "webhook_url"),
    ("feishu", "secret"),
    ("feishu", "app_secret"),
    ("pushplus", "token"),
    ("tushare", "token"),
]


def main():
    parser = argparse.ArgumentParser(description="Migrate plaintext settings to encrypted values")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview changes without writing to disk")
    args = parser.parse_args()

    script_dir = _SCRIPT_DIR
    settings_path = script_dir.parent / "config" / "settings.json"
    backup_path = settings_path.with_suffix(settings_path.suffix + ".bak.before_encrypt")

    with open(settings_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    changed = 0
    for section, key in SENSITIVE_FIELDS:
        if section not in raw:
            continue
        val = raw[section].get(key)
        if not isinstance(val, str) or val == "":
            continue
        if val.startswith("fenc:"):
            continue
        cipher = encrypt_str(val)
        print(f"[ENCRYPT] {section}.{key}: {val} -> {cipher}")
        raw[section][key] = cipher
        changed += 1

    if changed == 0:
        print("[OK] 没有需要加密的明文字段")
        return

    if args.dry_run:
        print(f"[DRY-RUN] 将修改 {changed} 个字段，未实际写盘")
        return

    if not backup_path.exists():
        shutil.copy2(settings_path, backup_path)
        # 备份文件含明文敏感字段：锁权限到仅本用户可读，防止其他系统用户偷窥
        try:
            os.chmod(backup_path, 0o400)
        except Exception:
            pass
        print(f"[BACKUP] -> {backup_path} (chmod 0400)")
        print("[WARN] 备份文件中包含未加密的原始 API Key/Webhook Secret 等敏感字段。")
        print("[WARN] 确认迁移正常后请手动删除此备份文件：rm", backup_path)

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)

    print(f"[DONE] 已加密 {changed} 个字段，写回 {settings_path}")


if __name__ == "__main__":
    main()
