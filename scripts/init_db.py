#!/usr/bin/env python3
"""FinAgentOS — 数据库初始化脚本
终端执行：python3 scripts/init_db.py

如果 finagentos 数据库或表不存在，会逐个创建。
如果已存在，会显示"already exists"。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from pymysql.cursors import DictCursor


def get_raw_conn():
    return pymysql.connect(
        unix_socket="/tmp/mysql.sock",
        user="root", password="",
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def create_database():
    conn = get_raw_conn()
    with conn.cursor() as cur:
        cur.execute("CREATE DATABASE IF NOT EXISTS finagentos "
                     "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()
    print("[OK] database 'finagentos' ready")


def run_schema():
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock", user="root", password="",
        database="finagentos", charset="utf8mb4", cursorclass=DictCursor,
    )
    tables = []

    def t(name, sql):
        with conn.cursor() as cur:
            cur.execute(f"SHOW TABLES LIKE '{name}'")
            if cur.fetchone():
                tables.append(f"{name:30s}  (already exists)")
                return
            for stmt in sql.split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s + ";")
            tables.append(f"{name:30s}  created")
        conn.commit()

    # 按外键依赖顺序建表（先建无依赖的表）
    t("users", '''
        CREATE TABLE users (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'USER',
            is_active TINYINT(1) DEFAULT 1,
            password_changed_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("workspaces", '''
        CREATE TABLE workspaces (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(500) DEFAULT '',
            is_default TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at DATETIME NULL,
            INDEX idx_ws_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("sub_accounts", '''
        CREATE TABLE sub_accounts (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            workspace_id BIGINT NOT NULL,
            name VARCHAR(100) NOT NULL,
            initial_capital DECIMAL(15,2) DEFAULT 0.00,
            current_cash DECIMAL(15,2) DEFAULT 0.00,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at DATETIME NULL,
            INDEX idx_sa_workspace (workspace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("refresh_tokens", '''
        CREATE TABLE refresh_tokens (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            token VARCHAR(500) NOT NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rt_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("agents", '''
        CREATE TABLE agents (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_type VARCHAR(30) NOT NULL,
            name VARCHAR(200) NOT NULL,
            workspace_id BIGINT NOT NULL,
            sub_account_id BIGINT NULL,
            llm_config JSON,
            status VARCHAR(20) DEFAULT 'ACTIVE',
            metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at DATETIME NULL,
            INDEX idx_agents_workspace (workspace_id),
            INDEX idx_agents_type (agent_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("orders", '''
        CREATE TABLE orders (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            trace_id VARCHAR(36) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            symbol_name VARCHAR(50),
            direction VARCHAR(4) NOT NULL,
            order_type VARCHAR(6) DEFAULT 'MARKET',
            price DECIMAL(10,3) NULL,
            quantity INT NOT NULL,
            status VARCHAR(10) DEFAULT 'PENDING',
            fill_price DECIMAL(10,3) NULL,
            reject_reason VARCHAR(200) NULL,
            audit_hash VARCHAR(64) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_orders_agent (agent_id),
            INDEX idx_orders_trace (trace_id),
            INDEX idx_orders_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("positions", '''
        CREATE TABLE positions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            symbol_name VARCHAR(50),
            quantity INT NOT NULL DEFAULT 0,
            avg_cost DECIMAL(10,3) NOT NULL DEFAULT 0,
            current_price DECIMAL(10,3) NULL,
            market_value DECIMAL(15,2) NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_pos_agent_symbol (agent_id, symbol)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("nav_snapshots", '''
        CREATE TABLE nav_snapshots (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            snapshot_date DATE NOT NULL,
            total_asset DECIMAL(15,2) NOT NULL,
            daily_return DECIMAL(8,6) NULL,
            cumulative_return DECIMAL(8,6) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_nav_agent_date (agent_id, snapshot_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("watchlists", '''
        CREATE TABLE watchlists (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            symbol_name VARCHAR(50) NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_wl_agent_symbol (agent_id, symbol)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("stop_loss_orders", '''
        CREATE TABLE stop_loss_orders (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            trace_id VARCHAR(36) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            symbol_name VARCHAR(50),
            trigger_price DECIMAL(10,3) NOT NULL,
            quantity INT NOT NULL,
            status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE',
            triggered_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_slo_agent (agent_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("decision_cards", '''
        CREATE TABLE decision_cards (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id VARCHAR(36) NOT NULL,
            agent_id BIGINT NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            stock_name VARCHAR(50) NULL,
            action VARCHAR(10) NOT NULL,
            confidence DECIMAL(4,3) NULL,
            current_price DECIMAL(10,2) NULL,
            suggested_position DECIMAL(5,2) NULL,
            stop_loss_price DECIMAL(10,2) NULL,
            take_profit_price DECIMAL(10,2) NULL,
            reasoning TEXT,
            data_sources JSON,
            audit_hash VARCHAR(64) NULL,
            status VARCHAR(10) DEFAULT 'PENDING',
            market_cycle VARCHAR(50) NOT NULL DEFAULT '',
            sector VARCHAR(50) NOT NULL DEFAULT '',
            pattern VARCHAR(100) NOT NULL DEFAULT '',
            review_outcome JSON NULL,
            executed_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dc_trace (trace_id),
            INDEX idx_dc_agent (agent_id),
            INDEX idx_dc_symbol (symbol),
            INDEX idx_dc_status (status),
            INDEX idx_dc_cycle (market_cycle),
            INDEX idx_dc_sector (sector)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("audit_chain", '''
        CREATE TABLE audit_chain (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id VARCHAR(36) NOT NULL,
            agent_type VARCHAR(30) NOT NULL,
            agent_id BIGINT NULL,
            action_type VARCHAR(50) NOT NULL,
            payload JSON NOT NULL,
            previous_hash VARCHAR(64) NOT NULL,
            current_hash VARCHAR(64) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_ac_trace (trace_id),
            INDEX idx_ac_hash (current_hash),
            INDEX idx_ac_prev (previous_hash)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("circuit_breaker_events", '''
        CREATE TABLE circuit_breaker_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id VARCHAR(36) NOT NULL,
            agent_id BIGINT NOT NULL,
            trigger_reason VARCHAR(100) NOT NULL,
            threshold_value DECIMAL(10,4) NULL,
            current_value DECIMAL(10,4) NULL,
            action_taken VARCHAR(100) NOT NULL,
            resolved_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cbe_agent (agent_id),
            INDEX idx_cbe_trace (trace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("factor_library", '''
        CREATE TABLE factor_library (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            factor_name VARCHAR(100) NOT NULL UNIQUE,
            formula TEXT NOT NULL,
            source VARCHAR(100) NULL,
            category VARCHAR(50) NULL,
            ic_mean DECIMAL(8,6) NULL,
            ic_ir DECIMAL(8,6) NULL,
            oos_ic DECIMAL(8,6) NULL,
            is_active TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_fl_category (category),
            INDEX idx_fl_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("factor_ic_records", '''
        CREATE TABLE factor_ic_records (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            factor_id BIGINT NOT NULL,
            test_date DATE NOT NULL,
            ic_value DECIMAL(8,6) NULL,
            rank_ic DECIMAL(8,6) NULL,
            is_oos TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fir_factor (factor_id),
            INDEX idx_fir_date (test_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("skill_exports", '''
        CREATE TABLE skill_exports (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            skill_id VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            agent_id BIGINT NULL,
            version VARCHAR(20) NOT NULL,
            strategy_type VARCHAR(50) NULL,
            perf_summary JSON,
            file_path VARCHAR(500) NULL,
            export_count INT DEFAULT 0,
            last_exported_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("decision_logs", '''
        CREATE TABLE decision_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id VARCHAR(36) NOT NULL,
            agent_id BIGINT NOT NULL,
            agent_type VARCHAR(30) NOT NULL,
            input_summary JSON,
            output_summary JSON,
            confidence DECIMAL(4,3) NULL,
            latency_ms INT NULL,
            status VARCHAR(20) DEFAULT 'SUCCESS',
            error_message TEXT NULL,
            token_cost INT DEFAULT 0,
            audit_hash VARCHAR(64) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dl_trace (trace_id),
            INDEX idx_dl_agent (agent_id),
            INDEX idx_dl_type (agent_type),
            INDEX idx_dl_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("system_alerts", '''
        CREATE TABLE system_alerts (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            alert_type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            source VARCHAR(100) NULL,
            message TEXT NULL,
            details JSON,
            is_resolved TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME NULL,
            INDEX idx_sa_type (alert_type),
            INDEX idx_sa_severity (severity),
            INDEX idx_sa_resolved (is_resolved)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("data_source_status", '''
        CREATE TABLE data_source_status (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            source_name VARCHAR(50) NOT NULL UNIQUE,
            status VARCHAR(10) NOT NULL DEFAULT 'ONLINE',
            latency_ms INT DEFAULT 0,
            last_success_at DATETIME NULL,
            last_error_at DATETIME NULL,
            error_count INT DEFAULT 0,
            check_count INT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    t("task_runs", '''
        CREATE TABLE task_runs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL UNIQUE,
            task_type VARCHAR(30) NOT NULL,
            trigger_type VARCHAR(10) NOT NULL DEFAULT 'SCHEDULED',
            status VARCHAR(10) NOT NULL DEFAULT 'RUNNING',
            agent_type VARCHAR(30) NULL,
            input_params JSON,
            output_summary JSON,
            error_message TEXT NULL,
            audit_hash VARCHAR(64) NULL,
            started_at DATETIME NULL,
            completed_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_tr_type (task_type),
            INDEX idx_tr_status (status),
            INDEX idx_tr_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    conn.close()
    print(f"
[OK] {len(tables)} tables processed")
    for t in tables:
        print(f"  {t}")


def seed_data():
    conn = pymysql.connect(
        unix_socket="/tmp/mysql.sock", user="root", password="",
        database="finagentos", charset="utf8mb4", cursorclass=DictCursor,
    )

    with conn.cursor() as cur:
        # 审计链起点（幂等）
        cur.execute("SELECT COUNT(*) as c FROM audit_chain WHERE trace_id='GENESIS'")
        if cur.fetchone()["c"] == 0:
            cur.execute(
                "INSERT INTO audit_chain (trace_id,agent_type,agent_id,action_type,payload,previous_hash,current_hash) "
                "VALUES (%s,%s,NULL,%s,%s,%s,%s)",
                ("GENESIS", "SYSTEM", "GENESIS", "{}", "0", "GENESIS"),
            )
            print("[OK] audit chain genesis inserted")

        # 数据源初始状态
        sources = [("akshare", "数据获取"), ("deepseek", "AI模型"), ("market_feed", "行情推送")]
        for name, label in sources:
            cur.execute("SELECT COUNT(*) as c FROM data_source_status WHERE source_name=%s", (name,))
            if cur.fetchone()["c"] == 0:
                cur.execute(
                    "INSERT INTO data_source_status (source_name, status) VALUES (%s, %s)",
                    (name, "ONLINE"),
                )
                print(f"[OK] data source '{label}' added")

    conn.commit()
    conn.close()
    print("[OK] seed data done")


if __name__ == "__main__":
    print("=" * 55)
    print("FinAgentOS — 数据库初始化")
    print("=" * 55)
    create_database()
    run_schema()
    seed_data()
    print("=" * 55)
    print("DONE. 终端执行: python3 scripts/verify_data_layer.py")
