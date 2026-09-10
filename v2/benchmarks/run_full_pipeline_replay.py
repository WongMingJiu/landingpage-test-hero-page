#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5 Full Pipeline Replay harness (V1).

从原始广告视频开始 fresh 跑完整链路，验证 Frozen V2.1a / V2.1b / V2.3 / T1 / T2
能否在真实生产路径中稳定串联：

    raw video -> fresh V2.1a -> fresh V2.1b -> fresh V2.3 -> fresh T1/T2 Hero

Frozen 中间 JSON 只用于 Compare / Evaluation，绝不作为生成输入（§4）。

设计原则（§5 Wiring existing modules, not rewriting modules）：
  - V2.1a/V2.1b/V2.3 通过已有 CLI 以 subprocess 调用（python -m v2.*）；
  - V2.3 fresh gate 直接复用 V2.3 benchmark runner 的 evaluate_creative；
  - Hero 生成复用上一轮 E2E 验证过的工程护栏（NO_PROXY 直连 + 墙钟看门狗 +
    size chain + ratio 判定 + resume），以 --_hero-worker 子进程隔离 env；
  - 本 harness 只负责 orchestrate / path management / trace persistence /
    validation / comparison / bounded engineering retry。

Frozen discipline（§18）：Build Once -> Run Once -> Compare -> Report -> Stop。
工程重试（timeout / network / JSON transport / provider 5xx）bounded 且记录；
语义重试禁止。

用法：
    python -m v2.benchmarks.run_full_pipeline_replay --phase preflight
    python -m v2.benchmarks.run_full_pipeline_replay --phase all
    # 断点续跑：默认 skip 已存在的有效 stage 输出；--force 强制重跑
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from v2.tagging import ApiClient, TaggingConfig, extract_json  # noqa: E402,F401
from v2.benchmarks.run_message_match_copy_benchmark import (  # noqa: E402
    evaluate_creative, _norm,
)

# --------------------------------------------------------------------------- #
# 路径 / 常量
# --------------------------------------------------------------------------- #
RUNS_ROOT = _REPO / "output" / "benchmark-runs"
VIDEOS_DIR = _REPO / "benchmarks-local" / "singing-creative-tagging-v1.0" / "videos"
CONFIG_ENV = _REPO / "config.env"

# Frozen baselines（只读，仅用于 Compare）
FROZEN = {
    "v2.1a": RUNS_ROOT / "v2.1a-val-phase2",          # qwen3.7-plus E2E run
    "v2.1b": RUNS_ROOT / "intent-b2",                 # canonical V2.1b run
    "v2.3": RUNS_ROOT / "v2.3-message-match-copy-third-pass",  # Prompt V1.2 all-green
}
FROZEN_V23_PROMPT_SHA = "961cdadfe1e0"  # per singing-message-match-copy-v1.0/manifest.json

# provider/model 基准记录（来自各 frozen run 的 manifest / summary；drift 报告用）
FROZEN_PROVIDERS = {
    "v2.1a": {"model": "qwen3.7-plus", "api_base": "https://slb-v1.api.fan",
              "source": "v2.1a-val-phase2 (manifest note)"},
    "v2.1b": {"model": None, "api_base": "https://slb-v1.api.fan",
              "source": "intent-b2 未记录 model；同期 V2.3 first-pass 为 qwen3.8-max"},
    "v2.3": {"model": "qwen3.8-max", "api_base": "https://slb-v1.api.fan", "temperature": 0.0,
             "source": "third-pass summary.json"},
    "hero": {"model": "gpt-image-2", "api_base": "https://llm.gw.dachensky.com/v1/images/edits",
             "source": "上轮 E2E（output/e2e-dynamic-copy-hero）同端点"},
}

TEMPLATES = {
    "t1": {
        "prompt_md": _REPO / "v2" / "prompts" / "hero_template_t1.md",
        "reference": _REPO / "v2" / "templates" / "hero_template_t1" / "reference_v1.1.png",
        "slots": ["headline_line_1", "headline_line_2", "subheadline",
                  "benefit_1_title", "benefit_1_desc",
                  "benefit_2_title", "benefit_2_desc",
                  "benefit_3_title", "benefit_3_desc",
                  "benefit_4_title", "benefit_4_desc",
                  "bottom_banner_text"],
        "size_chain": ["1024x1536", "auto"],   # reference 原生 16 倍数
        "ref_size": (1024, 1536),
    },
    "t2": {
        "prompt_md": _REPO / "v2" / "prompts" / "hero_template_t2.md",
        "reference": _REPO / "v2" / "templates" / "hero_template_t2" / "reference_v1.0.png",
        "slots": ["headline_line_1", "headline_line_2", "badge_right",
                  "benefit_badge_1", "benefit_badge_2",
                  "benefit_badge_3", "benefit_badge_4",
                  "bottom_banner_text"],
        "size_chain": ["1024x1728", "auto"],   # 部分网关静默降级 auto，ratio 判定
        "ref_size": (1024, 1728),
    },
}

# 每阶段 subprocess 墙钟超时（秒）+ 外层工程重试次数（同一命令原样重跑）
STAGE_BUDGET = {
    "v2.1a": (1800, 1),   # whisper small + ffmpeg 抽帧 + staged 多模态调用
                          # gpt-5.5 思考型慢于 qwen：Stage1 4批 + Stage2 + 可能 extension
    "v2.1b": (900, 1),    # 3 次调用，单次 V2_INTENT_TIMEOUT=300（见 stage_v21b）
    "v2.3": (900, 1),     # 单次 LLM 调用（third-pass qwen 实测 ~60s/条；gpt-5.5 更慢）
    "hero": (1500, 1),    # worker 内部 size chain（3+1 attempts × 360s 看门狗）
}

# 生图层 fatal 硬阻断（与上轮 E2E harness 相同口径）
FATAL_ERROR_MARKERS = (
    "insufficient_user_quota", "额度不足",
    "invalid_api_key", "incorrect_api_key",
    "API 返回 401", "API 返回 403",
)
HARD_ATTEMPT_TIMEOUT = 360  # 上轮验证：正常生图 78~318s，360s = 上限余量


# --------------------------------------------------------------------------- #
# config / env
# --------------------------------------------------------------------------- #
def parse_env_file(path: Path) -> dict:
    cfg = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


def stage_env(extra: dict | None = None) -> dict:
    """子进程 env：当前进程 env + config.env 全量键值（等价 source config.env）。"""
    env = os.environ.copy()
    env.update(parse_env_file(CONFIG_ENV))
    if extra:
        env.update(extra)
    return env


def _load_text_config() -> dict:
    """当前文本层运行配置（provider/model drift 报告 + judge provider）。

    优先级与 stage_env 一致：config.env（用户维护的当前配置）优先于进程
    环境变量，仅在 config.env 未定义该键时才回落 os.environ——避免后台
    任务 shell 环境残留旧值时 judge 与 subprocess 用了不同 provider
    （实测命中：shell env 残留 slb 旧路由，导致 preflight probe 探了旧网关）。
    """
    cfg = parse_env_file(CONFIG_ENV)

    def pick(*keys: str) -> str:
        for k in keys:
            if cfg.get(k):
                return cfg[k]
        for k in keys:
            if os.environ.get(k):
                return os.environ[k]
        return ""

    return {
        "api_base": pick("V2_API_BASE_URL", "API_BASE_URL"),
        "api_key": pick("V2_API_KEY", "API_KEY"),
        "model": pick("V2_MODEL_NAME", "MODEL_NAME"),
    }


# --------------------------------------------------------------------------- #
# subprocess stage runner（bounded engineering retry + console log 落盘）
# --------------------------------------------------------------------------- #
def run_stage(name: str, cmd: list[str], env: dict, timeout: int, retries: int,
              log_path: Path) -> dict:
    """跑一个 stage subprocess：墙钟超时 -> 杀进程；失败原样重试（工程重试）。

    返回 {status: ok|timeout|failed, returncode, elapsed_s, retries_used, last_error}
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    attempt_meta = []
    for attempt in range(1, retries + 2):
        t0 = time.time()
        print(f"[{name}] attempt {attempt}/{retries + 1}: "
              + " ".join(str(c) for c in cmd[:6]) + (" ..." if len(cmd) > 6 else ""),
              flush=True)
        try:
            proc = subprocess.run(
                cmd, cwd=str(_REPO), env=env,
                capture_output=True, text=True, timeout=timeout)
            elapsed = round(time.time() - t0, 1)
            log_path.write_text(
                f"$ {' '.join(str(c) for c in cmd)}\n\n--- stdout ---\n{proc.stdout}"
                f"\n--- stderr ---\n{proc.stderr}", encoding="utf-8")
            att = {"attempt": attempt, "returncode": proc.returncode, "elapsed_s": elapsed}
            attempt_meta.append(att)
            if proc.returncode == 0:
                att["status"] = "ok"
                print(f"[{name}] OK in {elapsed}s (retries_used={attempt - 1})", flush=True)
                return {"status": "ok", "retries_used": attempt - 1,
                        "elapsed_s": elapsed, "attempts": attempt_meta}
            err = (proc.stderr or proc.stdout or "")[-600:]
            att["status"] = "failed"
            att["error_tail"] = err[-300:]
            print(f"[{name}] FAILED rc={proc.returncode} in {elapsed}s: {err[-200:]}", flush=True)
            last = {"returncode": proc.returncode, "error": err}
        except subprocess.TimeoutExpired as e:
            elapsed = round(time.time() - t0, 1)
            err = f"stage wall-clock timeout >{timeout}s (subprocess killed)"
            attempt_meta.append({"attempt": attempt, "status": "timeout", "elapsed_s": elapsed})
            print(f"[{name}] {err}", flush=True)
            last = {"returncode": None, "error": err}
            if e.stdout or e.stderr:
                try:
                    log_path.write_text(
                        f"$ {' '.join(str(c) for c in cmd)}\n\n--- timeout {timeout}s ---\n"
                        f"--- stdout ---\n{e.stdout}\n--- stderr ---\n{e.stderr}",
                        encoding="utf-8")
                except Exception:
                    pass
        time.sleep(3.0)
    return {"status": "failed", "retries_used": retries,
            "attempts": attempt_meta, "last_error": last["error"],
            "returncode": last["returncode"]}


# --------------------------------------------------------------------------- #
# Hero worker（subprocess 隔离：NO_PROXY 直连 + 看门狗 + size chain）
# 复用上轮 output/e2e-dynamic-copy-hero/run_e2e.py 已验证的护栏模式
# --------------------------------------------------------------------------- #
def extract_body(md_text: str) -> str:
    m = re.search(r"^<!-- BEGIN RUNTIME PROMPT -->\n(.*?)\n^<!-- END RUNTIME PROMPT -->",
                  md_text, re.S | re.M)
    if not m:
        raise RuntimeError("runtime prompt markers not found")
    return m.group(1)


def parse_contract(md_text: str) -> dict:
    blk = re.search(r'"dynamic_slots":\s*\[(.*?)\]', md_text, re.S)
    if not blk:
        raise RuntimeError("dynamic_slots contract block not found")
    contract = {}
    for m in re.finditer(r'\{"name":\s*"([^"]+)".*?"max_chars":\s*(\d+)', blk.group(1)):
        contract[m.group(1)] = int(m.group(2))
    return contract


def render_prompt(body: str, slots: dict, names: list) -> str:
    out = body
    for s in names:
        out = out.replace("{{%s}}" % s, str(slots[s]))
    leftover = re.findall(r"\{\{[a-z_0-9]+\}\}", out)
    if leftover:
        raise RuntimeError(f"unresolved placeholders after render: {leftover}")
    return out


def preflight_slots(slots: dict, names: list, contract: dict) -> list:
    issues = []
    if set(slots) != set(names):
        issues.append(f"key mismatch extra={set(slots) - set(names)} "
                      f"missing={set(names) - set(slots)}")
        return issues
    for nm, val in slots.items():
        if not isinstance(val, str) or not val.strip():
            issues.append(f"{nm} empty/non-str: {val!r}")
            continue
        if "\n" in val:
            issues.append(f"{nm} newline: {val!r}")
        nc = len(re.sub(r"\s+", "", val))
        if nm in contract and nc > contract[nm]:
            issues.append(f"{nm} overbudget {nc}>{contract[nm]}: {val!r}")
    return issues


def _call_edit_with_hard_timeout(**kwargs):
    """daemon 线程 + join(360) 墙钟看门狗（上轮验证：requests 读超时对网关
    掐住长连接不发字节的场景不触发，实测挂 1431s；360s 弃用交上层重试）。"""
    box = {}

    def _work():
        try:
            # 延迟 import：generate_image 属生产 V1 模块，只在 worker 路径加载
            from generate_image import call_image_edit_api
            box["resp"] = call_image_edit_api(**kwargs)
        except BaseException as e:  # noqa: BLE001
            box["err"] = e

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(HARD_ATTEMPT_TIMEOUT)
    if th.is_alive():
        raise RuntimeError(f"hard wall-clock timeout >{HARD_ATTEMPT_TIMEOUT}s: "
                           f"gateway hung; abandoning attempt")
    if "err" in box:
        raise box["err"]
    return box["resp"]


def hero_worker_main(args) -> int:
    """--_hero-worker：生成一张 Hero（fresh V2.3 slots -> Frozen Runtime Prompt
    + Reference -> gpt-image-2）。在 NO_PROXY='*' 子进程里跑（绕过本地 Clash
    代理，上轮实测网关可直连且经代理会挂起空等）。"""
    # NO_PROXY='*'（大写是关键）必须在首次 requests 调用前设置
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    from generate_image import (  # noqa: E402  延迟 import：worker 子进程内加载
        load_config_env, CONFIG_PATH, call_image_edit_api, save_image_from_response,
    )
    from PIL import Image

    tpl = args.template
    tcfg = TEMPLATES[tpl]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.slots_json, encoding="utf-8") as f:
        slots = json.load(f)
    names = tcfg["slots"]
    md = tcfg["prompt_md"].read_text(encoding="utf-8")
    contract = parse_contract(md)

    issues = preflight_slots(slots, names, contract)
    if issues:
        (out_dir / "metadata.json").write_text(json.dumps(
            {"status": "preflight_failed", "issues": issues}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"[hero-worker/{tpl}] preflight FAILED: {issues}", flush=True)
        return 4

    prompt = render_prompt(extract_body(md), slots, names)
    (out_dir / "injected_prompt.md").write_text(prompt, encoding="utf-8")

    cfg = load_config_env(CONFIG_PATH)
    api_url, api_key = cfg["IMAGE_API_BASE_URL"], cfg["IMAGE_API_KEY"]
    model = cfg.get("IMAGE_MODEL_NAME", "gpt-image-2")
    ref = tcfg["reference"]
    ref_w, ref_h = tcfg["ref_size"]
    dst = out_dir / "output.png"

    meta = {"template": tpl, "provider": api_url, "model": model,
            "prompt_sha256_12": hashlib.sha256(prompt.encode()).hexdigest()[:12],
            "reference": str(ref.relative_to(_REPO)),
            "slots": slots, "size_attempts": []}
    ok = False
    for idx, size in enumerate(tcfg["size_chain"]):
        attempts = 3 if idx == 0 else 1
        for a in range(1, attempts + 1):
            t0 = time.time()
            att = {"size": size, "attempt": a}
            try:
                print(f"[hero-worker/{tpl}] {model} size={size} attempt {a}/{attempts}",
                      flush=True)
                resp = _call_edit_with_hard_timeout(
                    api_url=api_url, api_key=api_key, model=model,
                    prompt_text=prompt, image_paths=[ref], size=size, n=1)
                save_image_from_response(resp, dst)
                elapsed = round(time.time() - t0, 1)
                w, h = Image.open(dst).size
                att.update(status="ok", elapsed_s=elapsed, actual_size=f"{w}x{h}")
                meta["size_attempts"].append(att)
                meta.update(status="ok", requested_size=size, actual_size=f"{w}x{h}")
                meta["native_size"] = (w, h) == (ref_w, ref_h)
                meta["ratio_match"] = abs(w / h - ref_w / ref_h) / (ref_w / ref_h) < 0.01
                meta["ratio_diff_pct"] = round(
                    abs(w / h - ref_w / ref_h) / (ref_w / ref_h) * 100, 3)
                meta["elapsed_s"] = elapsed
                # §14：T2 非 native 不判失败；额外保存 normalized 1024x1728
                if not meta["native_size"]:
                    norm = Image.open(dst).resize((ref_w, ref_h), Image.LANCZOS)
                    norm.save(out_dir / "normalized_output.png")
                    meta["normalized_output"] = "normalized_output.png"
                ok = True
                print(f"[hero-worker/{tpl}] saved {w}x{h} in {elapsed}s "
                      f"(native={meta['native_size']} ratio_match={meta['ratio_match']})",
                      flush=True)
                break
            except Exception as e:
                elapsed = round(time.time() - t0, 1)
                err = str(e)[:300]
                att.update(status="failed", elapsed_s=elapsed, error=err)
                meta["size_attempts"].append(att)
                print(f"[hero-worker/{tpl}] size={size} attempt {a} FAILED "
                      f"after {elapsed}s: {err[:180]}", flush=True)
                if any(m in err for m in FATAL_ERROR_MARKERS):
                    meta.update(status="fatal_blocked")
                    (out_dir / "metadata.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                    return 5
                if a < attempts:
                    time.sleep(2.0 * (2 ** (a - 1)))
        if ok:
            break
    meta["status"] = "ok" if ok else "failed"
    (out_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 6


# --------------------------------------------------------------------------- #
# Preflight（§20）
# --------------------------------------------------------------------------- #
def probe_text_gateway(cfg: dict) -> tuple[bool, str]:
    try:
        client = ApiClient(cfg["api_base"], cfg["api_key"], cfg["model"], max_retries=1)
        raw = client.chat("你是探活检查。", [{"type": "text", "text": "回复一个词：OK"}])
        return True, f"chat ok, reply={raw.strip()[:20]!r}"
    except Exception as e:
        return False, str(e)[:300]


def probe_image_gateway() -> tuple[bool, str]:
    import requests
    cfg = parse_env_file(CONFIG_ENV)
    base = cfg.get("IMAGE_API_BASE_URL", "")
    models_url = re.sub(r"/images/edits$", "/models", base)
    try:
        # per-request proxies 覆盖 = 直连探活（不污染进程 env）
        r = requests.get(models_url, headers={"Authorization": f"Bearer {cfg['IMAGE_API_KEY']}"},
                         timeout=15, proxies={"http": None, "https": None})
        if r.status_code == 200:
            n = len(r.json().get("data", [])) if "data" in r.text[:200] else "?"
            return True, f"GET {models_url} 200 (models={n}, direct)"
        return False, f"GET {models_url} -> {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return False, str(e)[:300]


def preflight(creatives: list[str], run_dir: Path) -> dict:
    print("=" * 70)
    print("PREFLIGHT (§20)")
    print("=" * 70)
    results = {"ok": True, "checks": [], "drift": []}

    def check(name: str, ok: bool, detail: str) -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            results["ok"] = False

    # 1. source videos
    for vid in creatives:
        vp = VIDEOS_DIR / f"{vid}.mp4"
        check(f"video:{vid}", vp.is_file(),
              str(vp.relative_to(_REPO)) + (f" ({vp.stat().st_size // 1024 // 1024}MB)"
                                            if vp.is_file() else " MISSING"))

    # 2/3/4. 四层 API 可用性
    tcfg = _load_text_config()
    check("text-config", bool(tcfg["api_base"] and tcfg["api_key"] and tcfg["model"]),
          f"{tcfg['api_base']} model={tcfg['model']}")
    if tcfg["api_base"] and tcfg["api_key"] and tcfg["model"]:
        ok, detail = probe_text_gateway(tcfg)
        check("v2.1a/v2.1b/v2.3 API available", ok, detail)
    ok, detail = probe_image_gateway()
    check("gpt-image-2 endpoint available", ok, detail)

    # 5. T1/T2 references
    from PIL import Image
    for tpl, t in TEMPLATES.items():
        if t["reference"].is_file():
            w, h = Image.open(t["reference"]).size
            check(f"reference:{tpl}", (w, h) == t["ref_size"],
                  f"{t['reference'].name} {w}x{h} (expect {t['ref_size'][0]}x{t['ref_size'][1]})")
        else:
            check(f"reference:{tpl}", False, f"missing {t['reference']}")

    # 6. frozen prompts（存在 + V2.3 sha 校验）
    for p in ("v2/prompts/message_match_copy.md", "v2/prompts/creative_tagging.md",
              "v2/prompts/intent_decision.md", "v2/prompts/hero_template_t1.md",
              "v2/prompts/hero_template_t2.md"):
        fp = _REPO / p
        check(f"prompt:{p}", fp.is_file(), "found" if fp.is_file() else "MISSING")
    try:
        sha = hashlib.sha256(
            (_REPO / "v2/prompts/message_match_copy.md").read_bytes()).hexdigest()[:12]
    except OSError:
        sha = "<unreadable>"
    check("V2.3 prompt sha == frozen manifest", sha == FROZEN_V23_PROMPT_SHA,
          f"{sha} (manifest {FROZEN_V23_PROMPT_SHA})")

    # 7. frozen baselines（Compare 输入）
    for vid in creatives:
        paths = {
            "v2.1a": FROZEN["v2.1a"] / vid / "run0" / "v2" / "creative_tags.json",
            "v2.1b": FROZEN["v2.1b"] / vid / "creative_intent.json",
            "v2.3": FROZEN["v2.3"] / vid / "output.json",
        }
        for layer, p in paths.items():
            check(f"frozen:{layer}:{vid}", p.is_file(),
                  str(p.relative_to(_REPO)) if p.is_file() else "MISSING")

    # 8. output dir writable
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / ".write_test").write_text("x", encoding="utf-8")
        (run_dir / ".write_test").unlink()
        check("output dir writable", True, str(run_dir.relative_to(_REPO)))
    except Exception as e:
        check("output dir writable", False, str(e)[:120])

    # provider/model drift 报告（§19：报告，不静默替换）
    print("\n  -- provider/model drift --")
    cur = {
        "v2.1a": tcfg, "v2.1b": tcfg, "v2.3": tcfg,
        "hero": {"model": parse_env_file(CONFIG_ENV).get("IMAGE_MODEL_NAME", "gpt-image-2"),
                 "api_base": parse_env_file(CONFIG_ENV).get("IMAGE_API_BASE_URL", "")},
    }
    for layer, fz in FROZEN_PROVIDERS.items():
        c = cur[layer]
        if fz["model"] is None:
            drift = "unrecorded"
            note = f"frozen model 未记录；current={c['model']}（同期 V2.3 first-pass=qwen3.8-max）"
        elif fz["model"] == c["model"]:
            drift = "none"
            note = f"model 一致（{c['model']}）"
        else:
            drift = "MODEL DRIFT"
            note = f"frozen={fz['model']} -> current={c['model']}"
        results["drift"].append({"layer": layer, "frozen": fz["model"],
                                 "current": c["model"], "drift": drift, "note": note,
                                 "frozen_source": fz["source"]})
        print(f"  [{drift:^13}] {layer}: {note}")

    (run_dir / "preflight.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\npreflight -> {'PASS' if results['ok'] else 'FAIL'} "
          f"({sum(1 for c in results['checks'] if c['ok'])}/{len(results['checks'])} checks, "
          f"drift: {[d['drift'] for d in results['drift']]})")
    return results


# --------------------------------------------------------------------------- #
# Pipeline stages（§5/§7/§12：subprocess 调既有 CLI，trace 落盘）
# --------------------------------------------------------------------------- #
def stage_v21a(vid: str, vdir: Path, force: bool) -> dict:
    out = vdir / "v2.1a" / "creative_tags.json"
    if out.is_file() and not force:
        try:
            json.loads(out.read_text(encoding="utf-8"))
            return {"status": "skipped_existing", "out": str(out.relative_to(_REPO))}
        except Exception:
            pass
    video = VIDEOS_DIR / f"{vid}.mp4"
    # source.json：原始视频可追溯 artifact（§7）
    (vdir / "source.json").write_text(json.dumps({
        "creative_id": vid, "source_video": str(video.relative_to(_REPO)),
        "size_bytes": video.stat().st_size,
        "sha256_16": hashlib.sha256(video.read_bytes()).hexdigest()[:16],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    timeout, retries = STAGE_BUDGET["v2.1a"]
    res = run_stage(
        f"{vid}/v2.1a",
        [sys.executable, "-m", "v2.run_creative_tagging", str(video),
         "--creative-id", vid, "--output-dir", str(vdir / "v2.1a")],
        stage_env(), timeout, retries, vdir / "logs" / "v2.1a.log")
    res["out"] = str(out.relative_to(_REPO)) if out.is_file() else None
    return res


def stage_v21b(vid: str, vdir: Path, force: bool) -> dict:
    out = vdir / "v2.1b" / "creative_intent.json"
    if out.is_file() and not force:
        try:
            json.loads(out.read_text(encoding="utf-8"))
            return {"status": "skipped_existing", "out": str(out.relative_to(_REPO))}
        except Exception:
            pass
    timeout, retries = STAGE_BUDGET["v2.1b"]
    res = run_stage(
        f"{vid}/v2.1b",
        [sys.executable, "-m", "v2.intent_decision",
         "--tags", str(vdir / "v2.1a" / "creative_tags.json"),
         "--output-dir", str(vdir / "v2.1b")],
        # gpt-5.5 思考型慢响应：内置 90s TimeoutApiClient 会误杀，放宽到 300s
        stage_env({"V2_INTENT_TIMEOUT": "300"}),
        timeout, retries, vdir / "logs" / "v2.1b.log")
    res["out"] = str(out.relative_to(_REPO)) if out.is_file() else None
    return res


def stage_v23(vid: str, vdir: Path, force: bool) -> dict:
    out = vdir / "v2.3" / "message_match_copy.json"
    if out.is_file() and not force:
        try:
            json.loads(out.read_text(encoding="utf-8"))
            return {"status": "skipped_existing", "out": str(out.relative_to(_REPO))}
        except Exception:
            pass
    # input trace（对齐 third-pass 的 input.json 习惯）
    (vdir / "v2.3").mkdir(parents=True, exist_ok=True)
    (vdir / "v2.3" / "input.json").write_text(json.dumps({
        "creative_id": vid,
        "v2_1a_tags_path": str(vdir / "v2.1a" / "creative_tags.json"),
        "v2_1b_intent_path": str(vdir / "v2.1b" / "creative_intent.json"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    timeout, retries = STAGE_BUDGET["v2.3"]
    res = run_stage(
        f"{vid}/v2.3",
        [sys.executable, "-m", "v2.message_match_copy", "--creative-id", vid,
         "--tags", str(vdir / "v2.1a" / "creative_tags.json"),
         "--intent", str(vdir / "v2.1b" / "creative_intent.json"),
         "--out", str(out)],
        stage_env(), timeout, retries, vdir / "logs" / "v2.3.log")
    res["out"] = str(out.relative_to(_REPO)) if out.is_file() else None
    return res


def stage_hero(vid: str, vdir: Path, force: bool) -> dict:
    """两张 Hero（t1/t2）：fresh V2.3 slots -> Frozen Runtime Prompt。

    worker 以 NO_PROXY='*' 子进程跑（生图网关直连，上轮验证）；主进程 env
    不被污染（compare judge 仍走默认代理路径）。
    """
    from PIL import Image
    copy_doc = json.loads((vdir / "v2.3" / "message_match_copy.json")
                          .read_text(encoding="utf-8"))
    result = {}
    for tpl, tcfg in TEMPLATES.items():
        hdir = vdir / "hero" / tpl
        img = hdir / "output.png"
        if img.is_file() and not force:
            try:
                Image.open(img).verify()
                result[tpl] = {"status": "skipped_existing",
                               "out": str(img.relative_to(_REPO))}
                continue
            except Exception:
                pass
        slots_path = hdir / "slots.json"
        hdir.mkdir(parents=True, exist_ok=True)
        slots_path.write_text(json.dumps(
            copy_doc["output"][tpl]["slots"], ensure_ascii=False, indent=2),
            encoding="utf-8")
        timeout, retries = STAGE_BUDGET["hero"]
        res = run_stage(
            f"{vid}/hero/{tpl}",
            [sys.executable, "-m", "v2.benchmarks.run_full_pipeline_replay",
             "--_hero-worker", "--template", tpl,
             "--slots-json", str(slots_path), "--out-dir", str(hdir)],
            stage_env({"NO_PROXY": "*", "no_proxy": "*"}),
            timeout, retries, hdir.parent.parent / "logs" / f"hero_{tpl}.log")
        meta_p = hdir / "metadata.json"
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.is_file() else {}
        if res["status"] == "ok" and img.is_file():
            res["requested_size"] = meta.get("requested_size")
            res["actual_size"] = meta.get("actual_size")
            res["native_size"] = meta.get("native_size")
            res["ratio_match"] = meta.get("ratio_match")
        result[tpl] = res
    return result


# --------------------------------------------------------------------------- #
# Compare（§8-§11：Semantic Stability > String Equality）
# --------------------------------------------------------------------------- #
_JUDGE_V21A = """你是 V2.5 Full Pipeline Replay 的 V2.1a 语义稳定性判定器。
同一条广告视频跑了两次独立的 V2.1a Creative Tagging：FROZEN（冻结基准）与 FRESH（本轮）。
请比较核心语义，不要要求字符串完全一致：

1. semantic_stable —— 双方 active_value_tags（尤其 primary 层）核心价值主张是否语义一致；
   opening_type / user_expectation 是否同义或同为 taxonomy 内合理判定；decision_window 是否一致。
2. material_drift —— FRESH 是否产生了与视频内容不符的事实漂移（evidence 对应错误内容/时间），
   或丢掉 FROZEN 中的核心价值主张，或 primary 层换成完全不同的卖点。

口径：同义/近义标签（如「改善音色与声音质感」vs「改善音色」）= 稳定；
primary 层语义相同仅 supporting 层有差异 = 稳定；primary 换主张或证据对应错内容 = 不稳定。
只输出一个 JSON 对象，无解释文字：
{"semantic_stable": true|false, "material_drift": true|false,
 "differences": ["逐条列出实质差异，wording 级差异写明 wording-only"], "notes": "一句话总评"}"""

_JUDGE_V21B = """你是 V2.5 Full Pipeline Replay 的 V2.1b 语义稳定性判定器。
同一条广告跑了两次 V2.1b Intent Decision：FROZEN（冻结基准）与 FRESH（本轮，由本轮 FRESH V2.1a 输出驱动）。
请比较核心语义，不要要求字符串完全一致：

1. semantic_stable —— primary_driver 是否仍解释「同一个用户为什么点击」（同一点击因果）；
   unresolved_question 是否仍是同一个真正未解决的问题；intent_strength 是否同级。
2. material_drift —— supporting_drivers 是否实质漂移（换成了不同的支撑逻辑）。

口径：同一因果换措辞 = 稳定；点击因果本身改变（如从「怕学不会」变成「想变强」）= 不稳定。
只输出一个 JSON 对象，无解释文字：
{"semantic_stable": true|false, "material_drift": true|false,
 "differences": ["..."], "notes": "一句话总评"}"""

_JUDGE_V23 = """你是 V2.5 Full Pipeline Replay 的 V2.3 语义稳定性判定器。
同一条广告跑了两次 V2.3 Message Match Copy（均由各自轮次的 V2.1a/V2.1b 输出驱动）：
FROZEN（冻结基准）与 FRESH（本轮）。请比较，不要要求逐字一致：

1. anchor_preserved_t1 / anchor_preserved_t2 —— FRESH 的 T1/T2 是否保住与 FROZEN 相同的
   核心 Anchor（topics / phrases / user_concern / expectation 允许措辞不同，核心话题必须相同）。
2. intent_continuity_t1 / intent_continuity_t2 —— FRESH 是否仍在回答同一 intent。
3. template_differentiation —— FRESH 的 T1（问题→方法→四利益卡）与 T2（顾虑→适配→老师→学习支持）
   是否仍呈现不同销售结构（不是同义改写）。
4. same_answer_class —— 综合：FRESH 是否是「同一类正确答案」（文案可完全不同，但接住同一条广告）。

只输出一个 JSON 对象，无解释文字：
{"anchor_preserved_t1": true|false, "anchor_preserved_t2": true|false,
 "intent_continuity_t1": true|false, "intent_continuity_t2": true|false,
 "template_differentiation": true|false, "same_answer_class": true|false,
 "differences": ["..."], "notes": "一句话总评"}"""


def _run_compare_judge(api: ApiClient, system: str, user_text: str,
                       bool_fields: list[str], max_retries: int = 2) -> dict:
    """judge 调用：原生 boolean 严格校验（字符串/缺字段非法，绝不静默转换）。"""
    user = [{"type": "text", "text": user_text}]
    for attempt in range(1, max_retries + 1):
        raw = api.chat(system, user)
        try:
            verdict = extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[judge] parse failed (attempt {attempt}): {e}", flush=True)
            continue
        bad = [f for f in bool_fields if not isinstance(verdict.get(f), bool)]
        if bad:
            print(f"[judge] non-native boolean fields: {bad}", flush=True)
            continue
        return verdict
    raise RuntimeError("compare judge failed after bounded engineering retries")


def _tags_summary(tags: dict) -> str:
    lines = [f"decision_window: used={tags['decision_window'].get('used_seconds')}s "
             f"extended={tags['decision_window'].get('extended')}",
             f"opening_type: {tags['opening_type'].get('label')}",
             f"user_expectation: {tags['user_expectation'].get('label')}",
             "active_value_tags:"]
    for t in tags.get("matched_value_tags", []):
        ev = "；".join(e.get("content", "")[:40] for e in t.get("evidence", [])[:2])
        lines.append(f"  [{t.get('salience')}] {t.get('label')}（{t.get('category')}）"
                     f" evidence={ev[:80]}")
    return "\n".join(lines)


def _intent_summary(intent: dict) -> str:
    sup = "；".join(intent.get("supporting_drivers") or [])
    return (f"primary_driver: {intent['primary_driver']['statement']}\n"
            f"unresolved_question: {intent['unresolved_question']['statement']}\n"
            f"intent_strength: {intent.get('intent_strength')}\n"
            f"supporting_drivers: {sup or '-'}")


def _copy_summary(output: dict) -> str:
    a = output.get("creative_anchors", {})
    lines = [
        "creative_anchors:",
        f"  topics: {'、'.join(t.get('value', '') for t in a.get('topics', []))}",
        f"  phrases: {'、'.join(p.get('value', '') for p in a.get('phrases', []))}",
        f"  user_concern: {a.get('user_concern', {}).get('value', '')}",
        f"  expectation: {a.get('expectation', {}).get('value', '')}",
        f"grounding_status: {output.get('product_grounding_pack', {}).get('grounding_status')}",
    ]
    for side in ("t1", "t2"):
        lines.append(f"{side} slots:")
        lines.extend(f"  {k}: {v}" for k, v in output.get(side, {}).get("slots", {}).items())
    return "\n".join(lines)


def compare_creative(vid: str, vdir: Path, api: ApiClient, kb_norm: str) -> dict:
    """三层 frozen vs fresh：程序化 diff + 语义 judge。"""
    f_tags = json.loads((FROZEN["v2.1a"] / vid / "run0" / "v2" / "creative_tags.json")
                        .read_text(encoding="utf-8"))
    f_intent = json.loads((FROZEN["v2.1b"] / vid / "creative_intent.json")
                          .read_text(encoding="utf-8"))
    f_copy = json.loads((FROZEN["v2.3"] / vid / "output.json")
                        .read_text(encoding="utf-8"))["output"]
    r_tags = json.loads((vdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
    r_intent = json.loads((vdir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
    r_copy_doc = json.loads((vdir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))
    r_copy, r_meta = r_copy_doc["output"], r_copy_doc.get("meta", {})

    cmp_result: dict = {"creative_id": vid}

    # ---- V2.1a：程序化字段 diff ----
    prog = {
        "window_same": (f_tags["decision_window"].get("used_seconds")
                        == r_tags["decision_window"].get("used_seconds")
                        and f_tags["decision_window"].get("extended")
                        == r_tags["decision_window"].get("extended")),
        "opening_same": (f_tags["opening_type"].get("label")
                         == r_tags["opening_type"].get("label")),
        "expectation_same": (f_tags["user_expectation"].get("label")
                             == r_tags["user_expectation"].get("label")),
        "active_frozen": [t["label"] for t in f_tags.get("matched_value_tags", [])],
        "active_fresh": [t["label"] for t in r_tags.get("matched_value_tags", [])],
    }
    prog["active_primary_frozen"] = [t["label"] for t in f_tags.get("matched_value_tags", [])
                                     if t.get("salience") == "primary"]
    prog["active_primary_fresh"] = [t["label"] for t in r_tags.get("matched_value_tags", [])
                                    if t.get("salience") == "primary"]
    set_f, set_r = set(prog["active_frozen"]), set(prog["active_fresh"])
    prog["active_common"] = sorted(set_f & set_r)
    prog["active_only_frozen"] = sorted(set_f - set_r)
    prog["active_only_fresh"] = sorted(set_r - set_f)
    prog["primary_common"] = sorted(set(prog["active_primary_frozen"])
                                    & set(prog["active_primary_fresh"]))
    cmp_result["v2.1a_programmatic"] = prog
    try:
        cmp_result["v2.1a_judge"] = _run_compare_judge(
            api, _JUDGE_V21A,
            "【FROZEN V2.1a（冻结基准）】\n" + _tags_summary(f_tags)
            + "\n\n【FRESH V2.1a（本轮）】\n" + _tags_summary(r_tags)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["semantic_stable", "material_drift"])
    except Exception as e:
        cmp_result["v2.1a_judge"] = {"judge_failed": True, "error": str(e)[:200]}

    # ---- V2.1b ----
    try:
        cmp_result["v2.1b_judge"] = _run_compare_judge(
            api, _JUDGE_V21B,
            "【FROZEN V2.1b（冻结基准）】\n" + _intent_summary(f_intent)
            + "\n\n【FRESH V2.1b（本轮）】\n" + _intent_summary(r_intent)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["semantic_stable", "material_drift"])
    except Exception as e:
        cmp_result["v2.1b_judge"] = {"judge_failed": True, "error": str(e)[:200]}
    cmp_result["v2.1b_programmatic"] = {
        "strength_frozen": f_intent.get("intent_strength"),
        "strength_fresh": r_intent.get("intent_strength"),
    }

    # ---- V2.3：fresh gate（完整复用 V2.3 benchmark 的 A-D 程序化 gate）----
    from v2.benchmarks.run_message_match_copy_benchmark import _run_judge
    fresh_gate = None
    try:
        judge = _run_judge(api, r_tags, r_intent, r_copy)
        from v2.message_match_copy import MessageMatchCopyPipeline
        from v2 import message_match_schema as mms
        pipe = MessageMatchCopyPipeline(api)  # 只为拿 t1/t2 contract（prompt 只读）
        fresh_gate = evaluate_creative(
            r_copy, r_tags, r_intent, judge, kb_norm,
            pipe.t1_contract, pipe.t2_contract, mms.load_compliance_lists())
    except Exception as e:
        fresh_gate = {"gate_error": str(e)[:300]}
    cmp_result["v2.3_fresh_gate"] = fresh_gate

    # frozen vs fresh copy judge
    try:
        cmp_result["v2.3_judge"] = _run_compare_judge(
            api, _JUDGE_V23,
            "【FROZEN V2.3 Copy（冻结基准）】\n" + _copy_summary(f_copy)
            + "\n\n【FRESH V2.3 Copy（本轮）】\n" + _copy_summary(r_copy)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["anchor_preserved_t1", "anchor_preserved_t2", "intent_continuity_t1",
             "intent_continuity_t2", "template_differentiation", "same_answer_class"])
    except Exception as e:
        cmp_result["v2.3_judge"] = {"judge_failed": True, "error": str(e)[:200]}

    # anchors 程序化对照（wording-level，仅记录）
    def _anchors(o):
        a = o.get("creative_anchors", {})
        return {
            "topics": [t.get("value") for t in a.get("topics", [])],
            "phrases": [p.get("value") for p in a.get("phrases", [])],
            "user_concern": a.get("user_concern", {}).get("value"),
            "expectation": a.get("expectation", {}).get("value"),
        }
    cmp_result["v2.3_anchors_programmatic"] = {"frozen": _anchors(f_copy),
                                               "fresh": _anchors(r_copy),
                                               "fresh_generation_meta": r_meta}
    return cmp_result


# --------------------------------------------------------------------------- #
# Hero 程序化核验（§15 A/E + ROI crops 供人工 C/D/F）
# --------------------------------------------------------------------------- #
HERO_ROIS = {  # 与上轮 verify_e2e.py 相同的实测版式坐标
    "t1": {"headline": (0.03, 0.05, 0.97, 0.33), "subheadline": (0.04, 0.33, 0.96, 0.42),
           "benefits": (0.01, 0.42, 0.57, 0.88), "namebar": (0.85, 0.41, 0.99, 0.62),
           "banner": (0.00, 0.87, 1.00, 1.00)},
    "t2": {"headline": (0.03, 0.26, 0.97, 0.48), "badges": (0.03, 0.48, 0.62, 0.57),
           "benefits": (0.03, 0.57, 0.50, 0.85), "namebar": (0.82, 0.51, 0.99, 0.82),
           "banner": (0.00, 0.88, 1.00, 1.00)},
}


def verify_hero(vid: str, vdir: Path) -> dict:
    """ROI 裁剪放大（供逐字核）+ cv2 色板/几何核（零冷色漂移 / banner 高度）。"""
    import numpy as np
    from PIL import Image
    out = {}
    for tpl in TEMPLATES:
        hdir = vdir / "hero" / tpl
        img_p = hdir / "output.png"
        if not img_p.is_file():
            out[tpl] = {"status": "missing"}
            continue
        img = Image.open(img_p)
        w, h = img.size
        rec = {"size": f"{w}x{h}"}
        # ROI crops（放大 2-3x，禁整图读字）
        crops_dir = hdir / "crops"
        crops_dir.mkdir(exist_ok=True)
        rec["crops"] = {}
        for roi, (x0, y0, x1, y1) in HERO_ROIS[tpl].items():
            crop = img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
            up = 3 if roi in ("benefits", "badges", "namebar", "subheadline") else 2
            crop = crop.resize((crop.width * up, crop.height * up), Image.LANCZOS)
            cp = crops_dir / f"{roi}.png"
            crop.save(cp)
            rec["crops"][roi] = str(cp.relative_to(_REPO))
        # 色板（HSV 口径与上轮 E2E 相同）
        try:
            import cv2
            im = cv2.imread(str(img_p))
            hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
            H = hsv[..., 0].astype(int); S = hsv[..., 1].astype(int); V = hsv[..., 2].astype(int)
            rec["palette_pct"] = {
                "red": round((((H < 10) | (H > 170)) & (S > 90) & (V > 60)).mean() * 100, 1),
                "cream": round(((H < 35) & (S < 60) & (V > 150)).mean() * 100, 1),
                "cold": round(((H > 85) & (H < 160) & (S > 60)).mean() * 100, 2),
                "dark": round((V < 60).mean() * 100, 1),
            }
            band = hsv[int(h * 0.88):, :, :]
            Hb = band[..., 0].astype(int); Sb = band[..., 1].astype(int); Vb = band[..., 2].astype(int)
            rec["banner_red_pct"] = round(
                (((Hb < 10) | (Hb > 170)) & (Sb > 90) & (Vb > 60)).mean() * 100, 1)
        except ImportError:
            rec["palette_pct"] = None
        out[tpl] = rec
    return out


# --------------------------------------------------------------------------- #
# 判定（§16/§17）
# --------------------------------------------------------------------------- #
def judge_pipeline(vid: str, trace: dict, cmp_result: dict, hero_meta: dict,
                   hero_verify: dict) -> dict:
    """每 creative 一个 FULL_PIPELINE_{PASS|WARN|FAIL} + failure_layer 归因。"""
    verdict = {"creative_id": vid, "pipeline_status": None, "failure_layer": None,
               "reasons": [], "warns": []}
    # 注意：fail 与 warn 必须是两个独立列表（fail = warn = [] 会让两者别名同一
    # 对象，warn.append 直接污染 fail，曾导致全绿样本被误判 FAIL）
    fail: list = []
    warn: list = []

    # ---- V2.1a ----
    a = cmp_result.get("v2.1a_judge", {})
    if a.get("judge_failed"):
        warn.append("V2.1a compare judge 失败（人工判定待补）")
        v21a_stable = None
    else:
        v21a_stable = a.get("semantic_stable") and not a.get("material_drift")
        if a.get("material_drift"):
            fail.append("V2.1a material_drift: " + "; ".join(a.get("differences", [])[:2]))
        elif not a.get("semantic_stable"):
            fail.append("V2.1a 语义不稳定: " + "; ".join(a.get("differences", [])[:2]))
    verdict["v2.1a_semantic_stable"] = v21a_stable

    # ---- V2.1b ----
    b = cmp_result.get("v2.1b_judge", {})
    if b.get("judge_failed"):
        warn.append("V2.1b compare judge 失败（人工判定待补）")
        v21b_stable = None
    else:
        v21b_stable = b.get("semantic_stable") and not b.get("material_drift")
        if b.get("material_drift"):
            fail.append("V2.1b material_drift: " + "; ".join(b.get("differences", [])[:2]))
        elif not b.get("semantic_stable"):
            fail.append("V2.1b 点击因果实质改变: " + "; ".join(b.get("differences", [])[:2]))
    verdict["v2.1b_semantic_stable"] = v21b_stable

    # ---- V2.3 ----
    gate = cmp_result.get("v2.3_fresh_gate", {})
    v23_stable = None
    if "gate_error" in gate:
        fail.append("V2.3 fresh gate 执行失败: " + gate["gate_error"])
    else:
        units = gate.get("units", {})
        for side in ("t1", "t2"):
            u = units.get(side, {})
            if not u.get("schema_valid"):
                fail.append(f"V2.3 {side} schema invalid")
            if not u.get("slot_contract"):
                fail.append(f"V2.3 {side} slot contract violation")
            if not u.get("compliance"):
                fail.append(f"V2.3 {side} compliance violation")
            if not u.get("grounding_safe"):
                fail.append(f"V2.3 {side} grounding 越界/KB 弱引用")
        if gate.get("unsupported_anchors"):
            fail.append("V2.3 unsupported anchors: "
                        + str(gate["unsupported_anchors"])[:150])
        c = cmp_result.get("v2.3_judge", {})
        if c.get("judge_failed"):
            warn.append("V2.3 compare judge 失败（人工判定待补）")
        else:
            v23_stable = (c.get("anchor_preserved_t1") and c.get("anchor_preserved_t2")
                          and c.get("same_answer_class"))
            if not c.get("anchor_preserved_t1"):
                fail.append("V2.3 T1 丢核心 Anchor")
            if not c.get("anchor_preserved_t2"):
                fail.append("V2.3 T2 丢核心 Anchor")
            if not c.get("same_answer_class"):
                fail.append("V2.3 非同一类正确答案: " + (c.get("notes") or "")[:120])
            if not c.get("template_differentiation"):
                fail.append("V2.3 T1/T2 同质化")
    verdict["v2.3_semantic_stable"] = v23_stable

    # ---- Hero（§14：T2 非 native 不判失败，ratio 容差内即 PASS 候选）----
    for tpl in ("t1", "t2"):
        m = hero_meta.get(tpl, {})
        ok = m.get("status") == "ok" or m.get("status") == "skipped_existing"
        v = hero_verify.get(tpl, {})
        rec_ok = bool(m.get("ratio_match", v.get("ratio_match")))
        verdict[f"{tpl}_image_pass"] = bool(ok and rec_ok)
        if not ok:
            fail.append(f"{tpl.upper()} 生图失败")
        elif not rec_ok:
            fail.append(f"{tpl.upper()} ratio 超容差（requested={m.get('requested_size')} "
                        f"actual={m.get('actual_size')}）")
        else:
            if m.get("native_size") is False:
                warn.append(f"{tpl.upper()} native size auto fallback "
                            f"(requested={m.get('requested_size')} actual={m.get('actual_size')}；"
                            f"已另存 normalized_output.png)")
        # 工程重试后成功 -> WARN（§16；失败时不报，避免与 fail 矛盾）
        if m.get("retries_used") and ok:
            warn.append(f"{tpl.upper()} 生图经 {m['retries_used']} 次工程重试后成功")
        # 色板冷色漂移观察（T1 应恒 0；T2 青绿 badge 设计内 2.7-3.7%）
        pal = v.get("palette_pct") or {}
        cold = pal.get("cold")
        if cold is not None and tpl == "t1" and cold > 1.0:
            warn.append(f"T1 冷色漂移 cold={cold}%（上轮基准恒 0）")

    # stage 工程重试 -> WARN
    for stage in ("v2.1a", "v2.1b", "v2.3"):
        st = trace.get(stage, {})
        if st.get("status") == "timeout":
            fail.append(f"{stage} stage 超时（工程重试耗尽）")
        elif st.get("status") not in ("ok", "skipped_existing"):
            fail.append(f"{stage} stage 失败")
        elif st.get("retries_used"):
            warn.append(f"{stage} 经 {st['retries_used']} 次工程重试后成功")

    # ---- 汇总 ----
    if fail:
        verdict["pipeline_status"] = "FAIL"
        verdict["reasons"] = fail
        # failure layer 归因（§17）
        layer = "UNKNOWN"
        if any("V2.1a" in f for f in fail):
            layer = "V2.1A"
        elif any("V2.1b" in f for f in fail):
            layer = "V2.1B"
        elif any("grounding" in f or "unsupported" in f for f in fail):
            layer = "V2.3_GROUNDING"
        elif any("V2.3 T1" in f or "V2.3 非同一" in f for f in fail):
            layer = "V2.3_T1_COPY" if any("T1" in f for f in fail) else "V2.3_T2_COPY"
        elif any("V2.3" in f for f in fail):
            layer = "V2.3_ANCHOR"
        elif any("生图" in f or "ratio" in f or "IMAGE" in f for f in fail):
            layer = "IMAGE_T1" if any("T1" in f for f in fail) else "IMAGE_T2"
        elif any("超时" in f or "stage 失败" in f for f in fail):
            layer = "INFRA"
        verdict["failure_layer"] = layer
    elif warn:
        verdict["pipeline_status"] = "WARN"
        verdict["reasons"] = warn
    else:
        verdict["pipeline_status"] = "PASS"
    return verdict


# --------------------------------------------------------------------------- #
# summary / report
# --------------------------------------------------------------------------- #
def write_summary(run_id: str, creatives: list[str], verdicts: dict, pre: dict,
                  run_meta: dict) -> None:
    n_pass = sum(1 for v in verdicts.values() if v["pipeline_status"] == "PASS")
    n_warn = sum(1 for v in verdicts.values() if v["pipeline_status"] == "WARN")
    n_fail = sum(1 for v in verdicts.values() if v["pipeline_status"] == "FAIL")
    samples = {}
    for vid in creatives:
        v = verdicts[vid]
        samples[vid] = {
            "pipeline_status": v["pipeline_status"],
            "v2.1a_semantic_stable": v.get("v2.1a_semantic_stable"),
            "v2.1b_semantic_stable": v.get("v2.1b_semantic_stable"),
            "v2.3_semantic_stable": v.get("v2.3_semantic_stable"),
            "t1_image_pass": v.get("t1_image_pass"),
            "t2_image_pass": v.get("t2_image_pass"),
            "failure_layer": v.get("failure_layer"),
            "reasons": v.get("reasons"),
        }
    summary = {
        "run_id": run_id,
        "completed": len(verdicts),
        "samples": samples,
        "metrics": {
            "source_video_found": f"{sum(1 for c in creatives if (VIDEOS_DIR / f'{c}.mp4').is_file())}/{len(creatives)}",
            "v2.1a_semantic_stability": f"{sum(1 for v in verdicts.values() if v.get('v2.1a_semantic_stable'))}/{len(creatives)}",
            "v2.1b_semantic_stability": f"{sum(1 for v in verdicts.values() if v.get('v2.1b_semantic_stable'))}/{len(creatives)}",
            "v2.3_semantic_stability": f"{sum(1 for v in verdicts.values() if v.get('v2.3_semantic_stable'))}/{len(creatives)}",
            "t1_generation": f"{sum(1 for v in verdicts.values() if v.get('t1_image_pass'))}/{len(creatives)}",
            "t2_generation": f"{sum(1 for v in verdicts.values() if v.get('t2_image_pass'))}/{len(creatives)}",
            "full_pipeline_pass": f"{n_pass}/{len(creatives)}",
            "full_pipeline_warn": f"{n_warn}/{len(creatives)}",
            "full_pipeline_fail": f"{n_fail}/{len(creatives)}",
        },
        "provider_model_drift": pre.get("drift"),
        "run_meta": run_meta,
    }
    (RUNS_ROOT / run_id / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsummary.json written: metrics={json.dumps(summary['metrics'], ensure_ascii=False)}")


def write_report(run_id: str, creatives: list[str], run_dir: Path, verdicts: dict,
                 traces: dict, compares: dict, hero_verifies: dict, pre: dict,
                 run_meta: dict) -> None:
    L: list[str] = []
    L.append(f"# V2.5 Full Pipeline Replay Report — {run_id}")
    L.append("")
    L.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append(f"- 样本：{', '.join(creatives)}（3 videos × 2 templates = 6 Hero）")
    L.append(f"- 判定口径：Semantic Stability > String Equality（§8）；"
             f"Frozen 中间 JSON 仅用于 Compare（§4）")
    L.append("")

    # 1. Pipeline Construction
    L.append("## 1. Pipeline Construction（如何复用已有模块）")
    L.append("")
    L.append("- V2.1a：subprocess 调既有 CLI `python -m v2.run_creative_tagging`（零复制）")
    L.append("- V2.1b：subprocess 调既有 CLI `python -m v2.intent_decision`（零复制）")
    L.append("- V2.3：subprocess 调既有 CLI `python -m v2.message_match_copy`（零复制）")
    L.append("- V2.3 fresh gate：直接 import V2.3 benchmark runner 的 `evaluate_creative`"
             "（A schema / B slot contract / C compliance / D grounding 完整复用）")
    L.append("- Hero：`--_hero-worker` 子进程注入 `NO_PROXY='*'`，护栏（360s 墙钟看门狗 + "
             "size chain + bounded retry + fatal fast-fail）从上轮已验证的 "
             "`output/e2e-dynamic-copy-hero/run_e2e.py` 移植；Frozen Runtime Prompt / "
             "Reference 零修改")
    L.append("- Compare：程序化 diff + LLM judge（原生 boolean 严格校验）")
    L.append("")

    # 2. Environment
    L.append("## 2. Environment（provider / model / drift）")
    L.append("")
    L.append("| 层 | frozen 基准 | 当前运行 | drift |")
    L.append("|---|---|---|---|")
    for d in pre.get("drift", []):
        L.append(f"| {d['layer']} | {d['frozen'] or '未记录'} | {d['current']} | {d['drift']} |")
    L.append("")
    L.append(f"- 文本层（V2.1a/V2.1b/V2.3）：`{run_meta['text_api_base']}` "
             f"model=`{run_meta['text_model']}` temperature=0.0")
    L.append(f"- Hero：`{run_meta['image_api_base']}` model=`{run_meta['image_model']}`")
    L.append(f"- drift 说明：V2.1a frozen run（v2.1a-val-phase2）为 qwen3.7-plus，"
             f"当前 {run_meta['text_model']} —— 属已报告的 model drift，未做任何静默替换（§19）；"
             f"V2.3 frozen（third-pass）为 qwen3.8-max，当前 {run_meta['text_model']}"
             " —— 同为 model drift；V2.1b intent-b2 未记录"
             " model，已如实标注。文本层网关亦由 slb-v1.api.fan 切至 llm.gw.dachensky.com"
             "（原网关额度透支，用户指定新路由），比对结论需结合双重 drift 解读。")
    L.append("")

    # 3. Per Creative Trace
    L.append("## 3. Per Creative Trace")
    for vid in creatives:
        tr = traces.get(vid, {})
        L.append("")
        L.append(f"### {vid}")
        for stage in ("v2.1a", "v2.1b", "v2.3"):
            st = tr.get(stage, {})
            L.append(f"- **{stage}**: {st.get('status')} "
                     f"(retries={st.get('retries_used', 0)}, "
                     f"elapsed={st.get('elapsed_s', '-')}s, out={st.get('out')})")
        hero = tr.get("hero", {})
        for tpl in ("t1", "t2"):
            hm = hero.get(tpl, {})
            L.append(f"- **hero/{tpl}**: {hm.get('status')} "
                     f"(requested={hm.get('requested_size')} actual={hm.get('actual_size')} "
                     f"native={hm.get('native_size')} ratio_match={hm.get('ratio_match')})")
        # fresh 链路关键内容
        try:
            r_tags = json.loads((run_dir / vid / "v2.1a" / "creative_tags.json")
                                .read_text(encoding="utf-8"))
            L.append(f"  - fresh tagging: opening={r_tags['opening_type'].get('label')} / "
                     f"expectation={r_tags['user_expectation'].get('label')} / "
                     f"active={[t['label'] for t in r_tags.get('matched_value_tags', [])]}")
            r_intent = json.loads((run_dir / vid / "v2.1b" / "creative_intent.json")
                                  .read_text(encoding="utf-8"))
            L.append(f"  - fresh intent: primary={r_intent['primary_driver']['statement']} / "
                     f"question={r_intent['unresolved_question']['statement']}")
            r_copy = json.loads((run_dir / vid / "v2.3" / "message_match_copy.json")
                                .read_text(encoding="utf-8"))["output"]
            a = r_copy.get("creative_anchors", {})
            L.append(f"  - fresh anchors: topics={'、'.join(t.get('value','') for t in a.get('topics',[]))} "
                     f"phrases={'、'.join(p.get('value','') for p in a.get('phrases',[]))}")
            L.append(f"  - fresh T1 headline: {r_copy['t1']['slots']['headline_line_1']} / "
                     f"{r_copy['t1']['slots']['headline_line_2']}")
            L.append(f"  - fresh T2 headline: {r_copy['t2']['slots']['headline_line_1']} / "
                     f"{r_copy['t2']['slots']['headline_line_2']}")
        except Exception:
            pass

    # 4. Frozen vs Fresh
    L.append("")
    L.append("## 4. Frozen vs Fresh（核心语义是否稳定）")
    for vid in creatives:
        c = compares.get(vid, {})
        v = verdicts.get(vid, {})
        L.append("")
        L.append(f"### {vid} — {v['pipeline_status']}"
                 + (f"（failure_layer={v['failure_layer']}）" if v.get("failure_layer") else ""))
        prog = c.get("v2.1a_programmatic", {})
        L.append(f"- V2.1a：opening_same={prog.get('opening_same')} "
                 f"expectation_same={prog.get('expectation_same')} "
                 f"primary_common={prog.get('primary_common')} "
                 f"only_frozen={prog.get('active_only_frozen')} "
                 f"only_fresh={prog.get('active_only_fresh')}")
        ja = c.get("v2.1a_judge", {})
        if not ja.get("judge_failed"):
            L.append(f"  - judge: semantic_stable={ja.get('semantic_stable')} "
                     f"material_drift={ja.get('material_drift')} notes={ja.get('notes')}")
        jb = c.get("v2.1b_judge", {})
        if not jb.get("judge_failed"):
            L.append(f"- V2.1b judge: semantic_stable={jb.get('semantic_stable')} "
                     f"material_drift={jb.get('material_drift')} notes={jb.get('notes')}")
        jc = c.get("v2.3_judge", {})
        if not jc.get("judge_failed"):
            L.append(f"- V2.3 judge: anchor_t1={jc.get('anchor_preserved_t1')} "
                     f"anchor_t2={jc.get('anchor_preserved_t2')} "
                     f"same_answer_class={jc.get('same_answer_class')} "
                     f"TD={jc.get('template_differentiation')}")
        gate = c.get("v2.3_fresh_gate", {})
        if "gate_error" not in gate:
            L.append(f"- V2.3 fresh gate: units={json.dumps(gate.get('units', {}), ensure_ascii=False)} "
                     f"review_needed={gate.get('review_needed')}")
        for r in (v.get("reasons") or []):
            L.append(f"- {'FAIL' if v['pipeline_status'] == 'FAIL' else 'WARN'}: {r}")

    # 5. Hero Validation
    L.append("")
    L.append("## 5. Hero Validation（6 张）")
    for vid in creatives:
        hv = hero_verifies.get(vid, {})
        for tpl in ("t1", "t2"):
            rec = hv.get(tpl, {})
            pal = rec.get("palette_pct")
            L.append(f"- {vid}/{tpl}: size={rec.get('size')} "
                     f"palette={json.dumps(pal, ensure_ascii=False) if pal else 'n/a'} "
                     f"banner_red={rec.get('banner_red_pct')}% "
                     f"crops={list((rec.get('crops') or {}).keys())}")
    L.append("")
    L.append("> [PENDING-HUMAN] 文字逐字核（headline/badge/benefit/banner）、Layout 视觉核、"
             "Message Match 人工判断待人工 Read crops 后补录（§15 C/D/F）。")
    L.append("")

    # 6. Final Recommendation
    L.append("## 6. Final Recommendation")
    L.append("")
    L.append("> [PENDING-HUMAN] 待人工视觉核验完成后给出：系统是否已具备 "
             "「Raw Video → Dual Hero」基本生产能力；下一步是小流量实验还是先修某模块。")
    L.append("")

    (run_dir / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report.md written: {run_dir / 'report.md'}")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_full_pipeline_replay",
                                 description="V2.5 Full Pipeline Replay "
                                             "(raw video -> fresh V2.1a/b/3 -> dual hero)")
    ap.add_argument("--creative-ids", nargs="+", default=["v03", "v04", "v06"])
    ap.add_argument("--run-id", default="v2.5-full-pipeline-replay-first-pass")
    ap.add_argument("--phase", choices=["preflight", "run", "compare", "report", "all"],
                    default="all")
    ap.add_argument("--force", action="store_true",
                    help="disable skip-existing (default: resume from valid outputs)")
    ap.add_argument("--_hero-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--template", choices=["t1", "t2"], help=argparse.SUPPRESS)
    ap.add_argument("--slots-json", help=argparse.SUPPRESS)
    ap.add_argument("--out-dir", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._hero_worker:
        return hero_worker_main(args)

    creatives = args.creative_ids
    run_dir = RUNS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"V2.5 Full Pipeline Replay | run_id={args.run_id} | creatives={creatives}")
    print(f"phase={args.phase} force={args.force}")

    # ---------- preflight ----------
    if args.phase in ("preflight", "all"):
        pre = preflight(creatives, run_dir)
        if not pre["ok"]:
            print("\n!! preflight FAIL — 先报告，不半跑（§20）")
            return 2
        if args.phase == "preflight":
            return 0

    # ---------- pipeline ----------
    text_cfg = _load_text_config()
    img_cfg = parse_env_file(CONFIG_ENV)
    run_meta = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text_api_base": text_cfg["api_base"], "text_model": text_cfg["model"],
        "image_api_base": img_cfg.get("IMAGE_API_BASE_URL", ""),
        "image_model": img_cfg.get("IMAGE_MODEL_NAME", "gpt-image-2"),
        "frozen_baselines": {k: str(v.relative_to(_REPO)) for k, v in FROZEN.items()},
        "discipline": "Build Once -> Run Once -> Compare -> Report -> Stop; "
                      "engineering retries bounded+recorded; semantic retries forbidden",
    }
    traces: dict = {}
    if args.phase in ("run", "all"):
        for vid in creatives:
            vdir = run_dir / vid
            vdir.mkdir(parents=True, exist_ok=True)
            print("\n" + "=" * 70)
            print(f"PIPELINE {vid}")
            print("=" * 70)
            tr: dict = {}
            for stage_fn, key in ((stage_v21a, "v2.1a"), (stage_v21b, "v2.1b"),
                                  (stage_v23, "v2.3")):
                st = stage_fn(vid, vdir, args.force)
                tr[key] = st
                if st["status"] not in ("ok", "skipped_existing"):
                    print(f"!! {vid}/{key} -> {st['status']}，STOP that sample（后续层跳过）")
                    break
            else:
                tr["hero"] = stage_hero(vid, vdir, args.force)
            traces[vid] = tr
            (vdir / "trace.json").write_text(
                json.dumps(tr, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
        run_meta["finished_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---------- compare ----------
    compares: dict = {}
    hero_verifies: dict = {}
    verdicts: dict = {}
    if args.phase in ("compare", "report", "all"):
        api = ApiClient(text_cfg["api_base"], text_cfg["api_key"], text_cfg["model"],
                        temperature=0.0, max_retries=3)
        with open(_REPO / "docs" / "knowledge" / "singing-5day-experience-camp-kb-v1.0.md",
                  encoding="utf-8") as f:
            kb_norm = _norm(f.read())
        for vid in creatives:
            vdir = run_dir / vid
            if not (vdir / "v2.3" / "message_match_copy.json").is_file():
                print(f"[compare] {vid}: pipeline 未完成，跳过 compare")
                verdicts[vid] = {"creative_id": vid, "pipeline_status": "FAIL",
                                 "failure_layer": "UNKNOWN", "reasons": ["pipeline 未完成"]}
                continue
            print(f"\n[compare] {vid}")
            # judge 结果复用（Run Once 语义）：frozen_vs_fresh.json 已存在且含
            # v2.1a_judge 字段则直接读入，不重调 judge（gpt-5.5 非确定性重跑会
            # 得到不同判定，等于变相语义重试）；hero/trace 变化只影响 verdict 重算
            reuse_p = vdir / "compare" / "frozen_vs_fresh.json"
            if reuse_p.is_file():
                try:
                    cached = json.loads(reuse_p.read_text(encoding="utf-8"))
                    if "v2.1a_judge" in cached:
                        print(f"[compare] {vid}: reuse frozen_vs_fresh.json (judge as-is)")
                        cmp_r = cached
                    else:
                        raise ValueError("incomplete cache")
                except Exception:
                    cmp_r = compare_creative(vid, vdir, api, kb_norm)
            else:
                try:
                    cmp_r = compare_creative(vid, vdir, api, kb_norm)
                except Exception as e:
                    print(f"[compare] {vid} FAILED: {e}")
                    cmp_r = {"creative_id": vid, "compare_error": str(e)[:300]}
            compares[vid] = cmp_r
            (vdir / "compare").mkdir(exist_ok=True)
            (vdir / "compare" / "frozen_vs_fresh.json").write_text(
                json.dumps(cmp_r, ensure_ascii=False, indent=2), encoding="utf-8")
            hero_verifies[vid] = verify_hero(vid, vdir)
            # verdict
            tr = traces.get(vid) or json.loads((vdir / "trace.json").read_text(
                encoding="utf-8")) if (vdir / "trace.json").is_file() else {}
            hero_meta = (tr or {}).get("hero", {})
            # skipped_existing 的 hero 从 metadata.json 补齐 ratio/native
            for tpl in ("t1", "t2"):
                if hero_meta.get(tpl, {}).get("status") == "skipped_existing":
                    mp = vdir / "hero" / tpl / "metadata.json"
                    if mp.is_file():
                        m = json.loads(mp.read_text(encoding="utf-8"))
                        hero_meta[tpl].update(requested_size=m.get("requested_size"),
                                              actual_size=m.get("actual_size"),
                                              native_size=m.get("native_size"),
                                              ratio_match=m.get("ratio_match"))
            verdicts[vid] = judge_pipeline(vid, tr or {}, cmp_r, hero_meta,
                                           hero_verifies[vid])
            # report 阶段（run 未重跑）也要把恢复的 trace 写回，供 §3 trace 表格用
            traces[vid] = tr or {}
            (vdir / "compare" / "evaluation.json").write_text(
                json.dumps({"verdict": verdicts[vid],
                            "hero_verify": hero_verifies[vid]},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[verdict] {vid}: {verdicts[vid]['pipeline_status']} "
                  f"layer={verdicts[vid].get('failure_layer')} "
                  f"reasons={verdicts[vid].get('reasons')}")

    # ---------- summary / report ----------
    if args.phase in ("report", "all") and verdicts:
        pre = json.loads((run_dir / "preflight.json").read_text(encoding="utf-8"))
        write_summary(args.run_id, creatives, verdicts, pre, run_meta)
        write_report(args.run_id, creatives, run_dir, verdicts, traces, compares,
                     hero_verifies, pre, run_meta)
        print("\n" + "=" * 70)
        for vid in creatives:
            v = verdicts.get(vid, {})
            print(f"  {vid}: {v.get('pipeline_status')}"
                  + (f" (layer={v.get('failure_layer')})" if v.get("failure_layer") else ""))
        print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
