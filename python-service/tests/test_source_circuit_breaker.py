#!/usr/bin/env python3
"""数据中台：双源断路器状态机测试（不依赖网络/DB）。

覆盖：
1. 初始 closed 用主源（东财）
2. 主源失败未达阈值保持 closed
3. 达到阈值 → open（切新浪）
4. 冷却期内持续用备源
5. 冷却后 → half_open 用主源探测，成功 → closed（回切）
6. half_open 探测失败 → 立即回 open（防抖动）
7. 备源成功不误回切（open 保持，防乒乓）
8. 备源失败不影响熔断状态

运行方式：
    .venv/bin/python tests/test_source_circuit_breaker.py
    （安装 pytest 后亦可直接被 pytest 收集）
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.source_circuit_breaker import EASTMONEY, SINA, SourceCircuitBreaker


def test_initial_closed_uses_eastmoney():
    b = SourceCircuitBreaker()
    assert b.state == "closed"
    assert b.get_source() == EASTMONEY


def test_failures_below_threshold_keep_closed():
    b = SourceCircuitBreaker(failure_threshold=3)
    b.record_failure(EASTMONEY)
    b.record_failure(EASTMONEY)
    assert b.state == "closed"
    assert b.get_source() == EASTMONEY


def test_threshold_reached_opens_to_sina():
    b = SourceCircuitBreaker(failure_threshold=3)
    b.record_failure(EASTMONEY)
    b.record_failure(EASTMONEY)
    b.record_failure(EASTMONEY)
    assert b.state == "open"
    assert b.get_source() == SINA


def test_open_within_cooldown_keeps_sina():
    b = SourceCircuitBreaker(failure_threshold=3, recover_cooldown_s=600)
    b.record_failure(EASTMONEY)
    b.record_failure(EASTMONEY)
    b.record_failure(EASTMONEY)
    assert b.get_source() == SINA
    assert b.get_source() == SINA  # 冷却期内稳定走备源


def test_recover_success_closes_and_returns_to_eastmoney():
    b = SourceCircuitBreaker(failure_threshold=3, recover_cooldown_s=0.05)
    for _ in range(3):
        b.record_failure(EASTMONEY)
    time.sleep(0.06)
    assert b.get_source() == EASTMONEY  # half_open 探测
    assert b.state == "half_open"
    b.record_success(EASTMONEY)
    assert b.state == "closed"
    assert b.get_source() == EASTMONEY


def test_recover_failure_reopens_immediately():
    b = SourceCircuitBreaker(failure_threshold=3, recover_cooldown_s=0.05)
    for _ in range(3):
        b.record_failure(EASTMONEY)
    time.sleep(0.06)
    assert b.get_source() == EASTMONEY  # half_open 探测失败
    b.record_failure(EASTMONEY)
    assert b.state == "open"  # 一次失败即回熔断
    assert b.get_source() == SINA


def test_backup_success_does_not_close():
    """备源成功只重置失败计数，不误回切主源（防乒乓）。"""
    b = SourceCircuitBreaker(failure_threshold=3)
    for _ in range(3):
        b.record_failure(EASTMONEY)
    b.record_success(SINA)
    assert b.state == "open"
    assert b.get_source() == SINA


def test_backup_failure_does_not_affect_state():
    b = SourceCircuitBreaker(failure_threshold=3)
    b.record_failure(SINA)
    b.record_failure(SINA)
    assert b.state == "closed"
    assert b.get_source() == EASTMONEY


if __name__ == "__main__":
    tests = [
        test_initial_closed_uses_eastmoney,
        test_failures_below_threshold_keep_closed,
        test_threshold_reached_opens_to_sina,
        test_open_within_cooldown_keeps_sina,
        test_recover_success_closes_and_returns_to_eastmoney,
        test_recover_failure_reopens_immediately,
        test_backup_success_does_not_close,
        test_backup_failure_does_not_affect_state,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ❌ {t.__name__}: {exc}")
    if failed:
        print(f"\n{len(tests) - failed}/{len(tests)} 通过，{failed} 失败")
        sys.exit(1)
    print(f"\n全部 {len(tests)} 个断路器用例通过 ✅")
