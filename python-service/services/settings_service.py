import os, time, json
from shared.config import runtime_settings
from shared.crypto_utils import mask_api_key, encrypt_str, decrypt_str

SENSITIVE_FIELDS = [
    ("provider", "api_key"), ("feishu", "webhook_url"), ("feishu", "secret"),
    ("feishu", "app_secret"), ("pushplus", "token"), ("tushare", "token"),
    ("qwen", "api_key"),
]

def _section_keys(section): return {k for (s,k) in SENSITIVE_FIELDS if s==section}

def _mask_sensitive(plain: str) -> str:
    if not plain:
        return ""
    k = plain.strip()
    if len(k) <= 8:
        return "*" * len(k)
    prefixes = ["sk-", "pk-", "Bearer "]
    for pf in prefixes:
        if k.startswith(pf) and len(k) > len(pf) + 8:
            tail = k[len(pf):]
            if len(tail) <= 8:
                return pf + "*" * len(tail)
            masked_tail = "*" * (len(tail) - 4) + tail[-4:]
            return pf + masked_tail
    return k[:4] + "*" * (len(k) - 8) + k[-4:]

def _validate_patch(patch: dict) -> None:
    """CP-4.4: PUT 参数校验。任一失败抛 ValueError，磁盘不变更。"""
    provider = patch.get("provider", {})
    if isinstance(provider, dict):
        re_val = provider.get("reasoning_effort")
        if re_val is not None and re_val != "":
            if re_val not in {"low", "medium", "high"}:
                raise ValueError("reasoning_effort 只允许 low/medium/high")
        if "thinking" in provider:
            if not isinstance(provider["thinking"], bool):
                raise ValueError("provider.thinking 必须是 bool")

    general = patch.get("general", {})
    if isinstance(general, dict):
        ka_val = general.get("kline_adjust")
        if ka_val is not None:
            if ka_val not in {"qfq", "hfq", "none"}:
                raise ValueError("general.kline_adjust 只允许 qfq/hfq/none")

    scheduler = patch.get("scheduler", {})
    if isinstance(scheduler, dict):
        sp_val = scheduler.get("period")
        if sp_val is not None and sp_val != "":
            presets = {"daily", "weekday", "1min", "5min", "15min", "1h"}
            if sp_val not in presets:
                parts = str(sp_val).strip().split()
                if len(parts) < 5:
                    raise ValueError("scheduler.period 必须是 cron 风格(至少5个白空格分词)或 ∈ {daily, weekday, 1min, 5min, 15min, 1h}")

def get_view() -> dict:
    """返回 GET /api/settings 视图。敏感字段：xxx_masked + xxx_set；非敏感字段直接原值返回。"""
    snap = runtime_settings.snapshot_dict()
    out = {}
    for sec in ["provider","general","feishu","tushare","pushplus","scheduler"]:
        src = snap.get(sec, {})
        dst = {}
        sens_keys = _section_keys(sec)
        for k, v in src.items():
            if k.endswith("_encrypted"):
                continue
            if k in sens_keys:
                # 必须是字符串（密文或明文空串）
                if isinstance(v, str) and v != "":
                    # 先内存解密，再 mask
                    plain = decrypt_str(v) if v.startswith("fenc:") else v
                    dst[f"{k}_masked"] = _mask_sensitive(plain) if plain else ""
                    dst[f"{k}_set"] = True
                else:
                    dst[f"{k}_masked"] = ""
                    dst[f"{k}_set"] = False
            else:
                dst[k] = v
        out[sec] = dst
    return {
        "version": runtime_settings.version,
        **out,
    }

def update(body: dict) -> tuple:
    """PUT /api/settings：body 是 settings.json 顶层结构的部分 patch（字段可选）。
    约定：敏感字段 - 传明文 → 存密文；传 "" → 清空；传 null / 不传 → 保持原值。
    返回 (new_version, new_snapshot_view_dict)。"""
    patch = {}
    for sec in ["provider","general","feishu","tushare","pushplus","scheduler"]:
        if sec in body and isinstance(body[sec], dict):
            sec_patch = {}
            for k, v in body[sec].items():
                if v is None:
                    continue
                sec_patch[k] = v
            if sec_patch:
                patch[sec] = sec_patch
    _validate_patch(patch)
    new_v, _ = runtime_settings.update(patch)
    return new_v, get_view()

def test_provider(body: dict) -> dict:
    """POST /api/settings/test-provider：body {model?, base_url?, api_key?, thinking?, reasoning_effort?}
    api_key 优先级：body 明文 > get_plaintext_api_key()。
    不写盘，只调用 Deepseek /chat/completions 接口（model 要支持 reasoning，推荐 `deepseek-chat`，不传也可）。
    返回 {ok, latency_ms, provider, model, message?}。任何异常都不抛，都包在 ok=false 里。"""
    import httpx, time, json as _json
    model = body.get("model") or runtime_settings.snapshot_dict()["provider"].get("model", "deepseek-chat")
    base_url = body.get("base_url") or runtime_settings.snapshot_dict()["provider"].get("base_url", "https://api.deepseek.com")
    key_plain = body.get("api_key") if (body.get("api_key") is not None and body.get("api_key") != "") else runtime_settings.get_plaintext_api_key()
    if not key_plain:
        return {"ok": False, "latency_ms": 0, "provider": "deepseek", "model": model, "message": "API Key 未配置"}
    t0 = time.perf_counter()
    try:
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {"model": model, "messages": [{"role":"user","content":"只回复 OK 一个字，不要标点"}], "max_tokens": 4, "temperature": 0}
        with httpx.Client(timeout=15.0) as c:
            r = c.post(url, headers={"Authorization": f"Bearer {key_plain}", "Content-Type":"application/json"}, json=payload)
        lat = int((time.perf_counter()-t0)*1000)
        if r.status_code == 200:
            data = r.json()
            msg = data.get("choices",[{}])[0].get("message",{}).get("content","")
            return {"ok": True, "latency_ms": lat, "provider": "deepseek", "model": model, "message": f"成功 ({msg[:20]})"}
        else:
            body_preview = r.text[:300]
            return {"ok": False, "latency_ms": lat, "provider": "deepseek", "model": model, "message": f"HTTP {r.status_code}: {body_preview}"}
    except Exception as e:
        lat = int((time.perf_counter()-t0)*1000)
        return {"ok": False, "latency_ms": lat, "provider": "deepseek", "model": model, "message": f"Exception: {type(e).__name__}: {str(e)[:200]}"}

def test_notification(body: dict) -> dict:
    """POST /api/settings/test-notification：body {type: "feishu"|"pushplus", params:{...}}
    type=feishu: params {webhook_url, secret?} → 发送文本「FinAgentOS 连通性测试 (epoch_ms)」
    type=pushplus: params {token} → 发送文本「FinAgentOS 连通性测试」
    返回 {ok, latency_ms, type, message?}。不写盘。"""
    import httpx, time, hashlib, hmac, base64, json as _json, os, datetime
    t0 = time.perf_counter()
    typ = body.get("type", "feishu")
    try:
        if typ == "feishu":
            params = body.get("params", {}) or {}
            wh = params.get("webhook_url")
            if not wh:
                plain_wh = runtime_settings.get_plaintext("feishu.webhook_url") or ""
                if not plain_wh and runtime_settings.snapshot_dict().get("feishu",{}).get("enabled", False):
                    pass
                wh = plain_wh
            if not wh:
                return {"ok": False, "latency_ms": int((time.perf_counter()-t0)*1000), "type":"feishu", "message": "webhook_url 未提供且未保存"}
            ts = str(int(time.time()))
            secret = params.get("secret") or runtime_settings.get_plaintext("feishu.secret")
            sign = ""
            if secret:
                string_to_sign = f"{ts}\n{secret}"
                hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
                sign = base64.b64encode(hmac_code).decode("utf-8")
            text = f"FinAgentOS 连通性测试 {int(time.time()*1000)}"
            payload = {"msg_type":"text","content":{"text":text}}
            sep = "&" if "?" in wh else "?"
            url = wh if not (secret and sign) else f"{wh}{sep}timestamp={ts}&sign={sign}"
            with httpx.Client(timeout=15) as c:
                r = c.post(url, json=payload, headers={"Content-Type":"application/json"})
            lat = int((time.perf_counter()-t0)*1000)
            try: d = r.json()
            except Exception: d = {"raw": r.text[:200]}
            ok = r.status_code==200 and (d.get("StatusCode")==0 or d.get("code")==0 or d.get("StatusCode") is None and str(d.get("msg","")).lower() in ("success","ok",""))
            return {"ok": bool(ok), "latency_ms": lat, "type":"feishu", "message": f"HTTP {r.status_code} | {_json.dumps(d, ensure_ascii=False)[:120]}"}
        elif typ == "pushplus":
            params = body.get("params", {}) or {}
            token = params.get("token") or runtime_settings.get_plaintext("pushplus.token")
            if not token:
                return {"ok": False, "latency_ms": int((time.perf_counter()-t0)*1000), "type":"pushplus", "message": "pushplus token 未提供且未保存"}
            url = "https://www.pushplus.plus/send"
            payload = {"token": token, "title": "FinAgentOS 连通性测试", "content": f"这是一条测试消息 {int(time.time()*1000)}", "template": "txt"}
            with httpx.Client(timeout=15) as c:
                r = c.post(url, json=payload)
            lat = int((time.perf_counter()-t0)*1000)
            try: d = r.json()
            except Exception: d = {"raw": r.text[:200]}
            return {"ok": r.status_code==200 and (d.get("code")==200), "latency_ms": lat, "type":"pushplus", "message": f"HTTP {r.status_code} | {_json.dumps(d, ensure_ascii=False)[:120]}"}
        else:
            return {"ok": False, "latency_ms": 0, "type": typ, "message": f"unknown type: {typ}"}
    except Exception as e:
        lat = int((time.perf_counter()-t0)*1000)
        return {"ok": False, "latency_ms": lat, "type": typ, "message": f"Exception: {type(e).__name__}: {str(e)[:200]}"}

def validate_llm(body: dict) -> dict:
    """CP-4.5/6: validate_llm = test_provider 的增强别名。
    返回 {ok, latency_ms, provider, model, usage:{total_tokens,prompt_tokens,completion_tokens}, message, raw}。
    usage.* 若接口没返回则为 None；任何异常不抛，都包在 ok=false 里。"""
    import httpx, time, json as _json
    model = body.get("model") or runtime_settings.snapshot_dict()["provider"].get("model", "deepseek-chat")
    base_url = body.get("base_url") or runtime_settings.snapshot_dict()["provider"].get("base_url", "https://api.deepseek.com")
    key_plain = body.get("api_key") if (body.get("api_key") is not None and body.get("api_key") != "") else runtime_settings.get_plaintext_api_key()
    usage_empty = {"total_tokens": None, "prompt_tokens": None, "completion_tokens": None}
    if not key_plain:
        return {"ok": False, "latency_ms": 0, "provider": "deepseek", "model": model, "usage": usage_empty, "message": "API Key 未配置", "raw": None}
    t0 = time.perf_counter()
    try:
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {"model": model, "messages": [{"role":"user","content":"只回复 OK 一个字，不要标点"}], "max_tokens": 4, "temperature": 0}
        with httpx.Client(timeout=15.0) as c:
            r = c.post(url, headers={"Authorization": f"Bearer {key_plain}", "Content-Type":"application/json"}, json=payload)
        lat = int((time.perf_counter()-t0)*1000)
        if r.status_code == 200:
            data = r.json()
            msg = data.get("choices",[{}])[0].get("message",{}).get("content","")
            u = data.get("usage", {}) or {}
            usage = {
                "total_tokens": u.get("total_tokens"),
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
            }
            raw_safe = {k: v for k, v in data.items() if k != "usage"}
            return {"ok": True, "latency_ms": lat, "provider": "deepseek", "model": model, "usage": usage, "message": f"成功 ({msg[:20]})", "raw": raw_safe or None}
        else:
            body_preview = r.text[:300]
            try:
                raw_safe = r.json()
            except Exception:
                raw_safe = {"raw_text": body_preview}
            return {"ok": False, "latency_ms": lat, "provider": "deepseek", "model": model, "usage": usage_empty, "message": f"HTTP {r.status_code}: {body_preview}", "raw": raw_safe or None}
    except Exception as e:
        lat = int((time.perf_counter()-t0)*1000)
        return {"ok": False, "latency_ms": lat, "provider": "deepseek", "model": model, "usage": usage_empty, "message": f"Exception: {type(e).__name__}: {str(e)[:200]}", "raw": None}

def get_full_internal(auth_ok: bool) -> dict:
    """CP-4.8/9: 返回 settings.json 完整 + 敏感字段内存解密的 dict。
    auth_ok=False：直接抛 PermissionError。
    auth_ok=True：每个 SENSITIVE_FIELDS 位置都是解了密的明文（空串保持空串）。"""
    if not auth_ok:
        raise PermissionError("internal endpoint")
    snap = runtime_settings.snapshot_dict()
    out = {}
    for sec in ["provider","general","feishu","tushare","pushplus","scheduler"]:
        src = snap.get(sec, {})
        dst = {}
        sens_keys = _section_keys(sec)
        for k, v in src.items():
            if k.endswith("_encrypted"):
                continue
            if k in sens_keys:
                if isinstance(v, str) and v != "":
                    plain = decrypt_str(v) if v.startswith("fenc:") else v
                    dst[k] = plain
                else:
                    dst[k] = ""
            else:
                dst[k] = v
        out[sec] = dst
    out["version"] = runtime_settings.version
    return out
