"""News & Research module integration test.

Runs end-to-end without starting the FastAPI server:
 1. NewsSource (AkShare adapter) directly — real data
 2. news_service (DB CRUD + sync) — creates tables, writes, reads
 3. Simulates REST endpoints via news_svc.* functions

Usage:
    cd python-service
    .\\venv\\Scripts\\python.exe scripts/test_news_integration.py
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime

# Ensure python-service directory is on sys.path (for scripts/ subdir runs)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SEP = "=" * 70
SUB = "-" * 70


def hdr(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def sub(title: str):
    print(f"\n{SUB}")
    print(f"  {title}")
    print(SUB)


def show_rows(label: str, rows):
    if not rows:
        print(f"  [EMPTY] {label}")
        return
    print(f"  {label}: {len(rows)} rows")
    for i, r in enumerate(rows[:3]):
        print(f"\n  --- Sample #{i+1} ---")
        if hasattr(r, "to_dict"):
            d = r.to_dict()
        elif isinstance(r, dict):
            d = r
        else:
            d = {k: getattr(r, k) for k in r.__dict__.keys() if not k.startswith("_")}
        for k, v in d.items():
            vs = str(v)
            if len(vs) > 80:
                vs = vs[:77] + "..."
            print(f"    {k}: {vs}")


# ============================================================
# Step 1: ensure DB tables exist
# ============================================================
hdr("Step 0: Init DB / Create tables")

# Use real MySQL (MySQL80 is running locally, matches project's production config)
from shared.config import _engine, settings
from shared.models import Base
print(f"  DB URL: {settings.DATABASE_URL}")
print(f"  Creating all tables via Base.metadata.create_all()...")
Base.metadata.create_all(_engine)
print("  OK")

# ============================================================
# Step 1: Test NewsSource adapter directly (real AkShare data)
# ============================================================
hdr("Step 1: Test NewsSource (AkShare adapter) DIRECT")

from data_source.news_source import NewsSource
ns = NewsSource()
ns.connect()
print("  NewsSource connected")

sub("1a. stock_news_em(600519) - 贵州茅台 个股新闻")
t0 = datetime.now()
try:
    items = ns.get_stock_news("600519")
    dt = (datetime.now() - t0).total_seconds()
    print(f"  OK in {dt:.2f}s: {len(items)} items")
    show_rows("NewsItem", items)
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("1b. stock_info_global_cls() - 财联社7x24电报")
t0 = datetime.now()
try:
    items = ns.get_global_telegraph()
    dt = (datetime.now() - t0).total_seconds()
    print(f"  OK in {dt:.2f}s: {len(items)} items")
    show_rows("NewsItem", items)
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("1c. stock_research_report_em() - 券商研报")
t0 = datetime.now()
try:
    reports = ns.get_research_reports(symbol=None, limit=20)
    dt = (datetime.now() - t0).total_seconds()
    print(f"  OK in {dt:.2f}s: {len(reports)} items")
    show_rows("ResearchReport", reports)
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

# ============================================================
# Step 2: Test news_service (DB CRUD + sync)
# ============================================================
hdr("Step 2: Test news_service (DB CRUD + sync)")

import services.news_service as news_svc

sub("2a. sync_all_news(symbols=[600519,000001])")
t0 = datetime.now()
try:
    stats = news_svc.sync_all_news(symbols=["600519", "000001"])
    dt = (datetime.now() - t0).total_seconds()
    print(f"  OK in {dt:.2f}s")
    for k, v in stats.items():
        print(f"    {k}: {v}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("2b. list_news(symbol=600519) - 查DB")
try:
    rows = news_svc.list_news(symbol="600519", days=30, limit=50, live_fetch=False)
    print(f"  DB news for 600519: {len(rows)} rows")
    for r in rows[:3]:
        print(f"    [{r['publish_time']}] {r['source']:<14s} | {r['title'][:60]}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("2c. list_news(source=cls_telegraph) - 财联社电报查DB")
try:
    rows = news_svc.list_news(source="cls_telegraph", days=7, limit=50, live_fetch=False)
    print(f"  DB cls_telegraph: {len(rows)} rows")
    for r in rows[:5]:
        print(f"    [{r['publish_time']}] {r['title'][:70]}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("2d. list_research_reports(symbol=000001) - 平安银行研报查DB")
try:
    rows = news_svc.list_research_reports(symbol="000001", days=365, limit=20, live_fetch=False)
    print(f"  DB reports for 000001: {len(rows)} rows")
    for r in rows[:5]:
        print(f"    [{r['publish_date']}] {r['institute']:<8s} {r['rating']:<6s} "
              f"EPS26={r['eps_2026']} PE26={r['pe_2026']} | {r['title'][:50]}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

# ============================================================
# Step 3: Live-fetch simulation (REST behavior without server)
# ============================================================
hdr("Step 3: Simulate REST API behavior (live-fetch on DB miss)")

sub('3a. list_news(symbol="300750") - 宁德时代 应该实时拉取')
try:
    rows = news_svc.list_news(symbol="300750", days=7, limit=20, live_fetch=True)
    print(f"  Live fetch result 300750: {len(rows)} rows")
    for r in rows[:3]:
        print(f"    [{r['publish_time']}] {r['source']} | {r['title'][:60]}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

sub("3b. list_research_reports(symbol=600519) - 茅台研报（实时拉取）")
try:
    rows = news_svc.list_research_reports(symbol="600519", days=365, limit=20, live_fetch=True)
    print(f"  Live fetch 茅台 reports: {len(rows)} rows")
    for r in rows[:5]:
        rating = r["rating"] or "N/A"
        eps26 = r["eps_2026"] or "N/A"
        print(f"    [{r['publish_date']}] {r['institute'] or 'N/A':<8s} {rating:<6s} EPS26={eps26} PE26={r['pe_2026']} | {r['title'][:45]}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(limit=2)

# ============================================================
# Summary
# ============================================================
hdr("SUMMARY")
print("""
  Files created/modified:
  1. [NEW]  data_source/news_source.py            — AkShare 资讯接口适配层
  2. [EDIT] shared/models.py                      — 新增 StockNews / ResearchReport
  3. [NEW]  services/news_service.py              — CRUD + 同步 + live fetch
  4. [EDIT] main.py                               — 新增 /api/news/list /api/research/list /api/news/sync
  5. [NEW]  scripts/test_news_integration.py      — 本测试脚本

  Quick manual test (once server is up):
    curl "http://localhost:8002/api/news/list?symbol=600519"
    curl "http://localhost:8002/api/news/list?source=cls_telegraph"
    curl "http://localhost:8002/api/research/list?symbol=000001&rating=买入"
    curl -X POST "http://localhost:8002/api/news/sync" \
         -H "Content-Type: application/json" \
         -d '{"symbols": ["600519", "000001"]}'
""")
