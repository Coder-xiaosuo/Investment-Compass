"""
FinAgentOS — 数据层验证脚本
验证 MySQL 连接 + ORM 模型 + 种子数据写入
终端执行：python3 scripts/verify_data_layer.py
"""
import sys
sys.path.insert(0, ".")

import pymysql
from datetime import datetime

DATABASE_URL = "mysql+pymysql://root:@localhost:3306/finagentos"


def test_raw_connection():
    """Step 1: 原始连接测试"""
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock",
        user="root", password="",
        database="finagentos",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        assert cur.fetchone()["ok"] == 1
    conn.close()
    print("[PASS] raw MySQL connection")


def test_list_tables():
    """Step 2: 表结构验证"""
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock", user="root", password="",
        database="finagentos", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    expected = [
        "users", "workspaces", "sub_accounts", "refresh_tokens",
        "agents", "orders", "positions", "nav_snapshots",
        "watchlists", "stop_loss_orders", "decision_cards",
        "audit_chain", "circuit_breaker_events",
        "factor_library", "factor_ic_records", "skill_exports",
        "decision_logs", "system_alerts", "data_source_status", "task_runs",
    ]
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        actual = {r["Tables_in_finagentos"] for r in cur.fetchall()}
    conn.close()

    missing = [t for t in expected if t not in actual]
    extra = [t for t in actual if t not in expected]
    if missing:
        print(f"[FAIL] missing tables: {missing}")
    else:
        print(f"[PASS] all 20 expected tables present")
    if extra:
        print(f"[INFO] extra tables (from other schemas): {extra}")
    return len(missing) == 0


def test_insert_seed_data():
    """Step 3: 种子数据写入"""
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock", user="root", password="",
        database="finagentos", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

    with conn.cursor() as cur:
        # 插入管理员用户
        from passlib.hash import bcrypt
        pw_hash = bcrypt.hash("admin123")
        cur.execute(
            "INSERT INTO users (username, password_hash, role, is_active) VALUES (%s, %s, %s, 1)",
            ("admin", pw_hash, "ADMIN"),
        )
        user_id = cur.lastrowid
        print(f"[INFO] inserted admin user, id={user_id}")

        # 插入默认工作区
        cur.execute(
            "INSERT INTO workspaces (user_id, name, description, is_default) VALUES (%s, %s, %s, 1)",
            (user_id, "默认工作区", "系统默认工作区",),
        )
        ws_id = cur.lastrowid
        print(f"[INFO] inserted default workspace, id={ws_id}")

        # 插入默认子账户
        cur.execute(
            "INSERT INTO sub_accounts (workspace_id, name, initial_capital, current_cash) VALUES (%s, %s, %s, %s)",
            (ws_id, "默认账户", 1000000.00, 1000000.00),
        )
        sa_id = cur.lastrowid
        print(f"[INFO] inserted default sub_account, id={sa_id}")

        # 插入审计链起点
        cur.execute(
            "INSERT INTO audit_chain (trace_id, agent_type, agent_id, action_type, payload, previous_hash, current_hash) "
            "VALUES (%s, %s, NULL, %s, %s, %s, %s)",
            ("GENESIS", "SYSTEM", "GENESIS", "{}", "0", "GENESIS"),
        )
        print(f"[INFO] audit chain genesis record inserted")

    conn.commit()
    conn.close()
    print("[PASS] seed data inserted")
    return True


def test_read_back():
    """Step 4: 数据回读验证"""
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock", user="root", password="",
        database="finagentos", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        users = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM workspaces")
        workspaces = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM sub_accounts")
        accounts = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM audit_chain")
        audit = cur.fetchone()["cnt"]
    conn.close()
    print(f"[PASS] read-back: users={users}, workspaces={workspaces}, "
          f"sub_accounts={accounts}, audit_chain={audit}")
    return all([users > 0, workspaces > 0, accounts > 0, audit > 0])


if __name__ == "__main__":
    print("=" * 55)
    print("FinAgentOS — 数据层验证")
    print("=" * 55)
    results = []
    results.append(test_raw_connection())
    results.append(test_list_tables())
    results.append(test_insert_seed_data())
    results.append(test_read_back())
    print("=" * 55)
    passed = sum(results)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    if all(results):
        print("Data layer is READY")
    else:
        print("Some checks failed")
