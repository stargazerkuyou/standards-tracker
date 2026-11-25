"""主程序：抓取各来源 → 去重 → AI 摘要 → 写 data/data.json 和 data/meta.json

本地运行：  cd scraper && python fetch.py
环境变量：
  GEMINI_API_KEY      设置了就用 Gemini 免费额度生成摘要
  ANTHROPIC_API_KEY   设置了（且没有 Gemini 密钥）就用 Claude（付费）
  两个都没有就只抓取、不生成摘要
  MAX_AI              每次最多生成多少条摘要（控制费用），默认 80
"""
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import now_iso  # noqa: E402
from sources import mof, ifrs, csrc  # noqa: E402
import summarize  # noqa: E402
import auto  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "data.json"
META = ROOT / "data" / "meta.json"
MAX_ITEMS = 3000
MAX_AI = int(os.environ.get("MAX_AI", "80"))

SOURCE_NAMES = {"mof": "财政部会计司", "ifrs": "IFRS 基金会（IASB / 解释委员会 / ISSB）", "csrc": "证监会（会计监管）"}


def load():
    if DATA.exists():
        return json.loads(DATA.read_text("utf-8"))
    return {"version": 1, "updated_at": None, "sources": {}, "items": []}


def apply_ai(item, ai):
    item["ai"] = ai
    if ai.get("type"):
        item["type"] = ai["type"]
    for s in ai.get("standards") or []:
        for k in ("cas", "ifrs"):
            v = s.get(k)
            if v:
                code = " ".join(v.split()[:2])  # "CAS 21 租赁" -> "CAS 21"
                if code not in item["standards"]:
                    item["standards"].append(code)


def main():
    db = load()
    items = {it["id"]: it for it in db["items"]}
    for it in items.values():          # 分类改名
        if it.get("framework") == "审计监管":
            it["framework"] = "监管"
    first_run = not items
    status = {}
    texts = {}        # 本次抓到的正文，供 AI 使用
    ai_budget = [MAX_AI]
    ai_errors = []
    ai_note = []

    def do_auto(it, text):
        try:
            old = it.get("auto") or {}
            new = auto.build(it, text, keep_title=old.get("title_zh"))
            new["v"] = 3
            it["auto"] = new
        except Exception as e:  # noqa: BLE001
            print("  自动摘要失败", it["url"], e)

    def try_ai(it, text):
        if ai_budget[0] <= 0 or not summarize.backend():
            return
        try:
            ai = summarize.summarize(it, text)
            if ai:
                apply_ai(it, ai)
                ai_budget[0] -= 1
        except summarize.RateLimited as e:
            print(f"  {e}，剩下的摘要下次运行再补")
            ai_note.append(str(e))
            ai_budget[0] = 0
        except Exception as e:  # noqa: BLE001
            print(f"  AI 摘要失败 {it['url']}: {e}")
            ai_errors.append(str(e)[:400])
            if len(ai_errors) >= 3 and not any(x.get("ai") for x in items.values()):
                ai_budget[0] = 0   # 连续失败、一条都没成功过：多半是配置问题，别浪费时间

    # ---------- 财政部 ----------
    errs, added = [], 0
    try:
        listed, errs = mof.fetch_list()
        for it in listed:
            if it["id"] in items:
                continue
            try:
                text, att = mof.fetch_detail(it)
                it["attachments"] = att
                texts[it["id"]] = text
            except Exception as e:  # noqa: BLE001
                errs.append(f"详情 {it['url']}: {e}")
                texts[it["id"]] = ""
            items[it["id"]] = it
            added += 1
            do_auto(it, texts[it["id"]])
            try_ai(it, texts[it["id"]])
    except Exception as e:  # noqa: BLE001
        errs.append(f"{e}\n{traceback.format_exc(limit=2)}")
    status["mof"] = {"name": SOURCE_NAMES["mof"], "added": added, "errors": errs[:10],
                     "ok": added > 0 or not errs, "checked_at": now_iso()}

    # ---------- 证监会 ----------
    errs, added, stats = [], 0, []
    try:
        listed, errs, stats = csrc.fetch_list()
        for it in listed:
            if it["id"] in items:
                continue
            try:
                text, att = csrc.fetch_detail(it)
                it["attachments"] = att
            except Exception as e:  # noqa: BLE001
                errs.append(f"详情 {it['url']}: {e}")
                text = ""
            texts[it["id"]] = text
            items[it["id"]] = it
            added += 1
            do_auto(it, text)
            try_ai(it, text)
    except Exception as e:  # noqa: BLE001
        errs.append(f"{e}\n{traceback.format_exc(limit=2)}")
    status["csrc"] = {"name": SOURCE_NAMES["csrc"], "added": added, "errors": errs[:10], "stats": stats,
                      "ok": bool(stats), "checked_at": now_iso()}   # 至少一个栏目读成功就算正常

    # ---------- IFRS ----------
    errs, added = [], 0
    try:
        new, errs = ifrs.fetch_new(set(items), months_back=6 if first_run else 3, limit=150)
        for it, text in new:
            items[it["id"]] = it
            texts[it["id"]] = text
            added += 1
            do_auto(it, text)
            try_ai(it, text)
    except Exception as e:  # noqa: BLE001
        errs.append(f"{e}\n{traceback.format_exc(limit=2)}")
    status["ifrs"] = {"name": SOURCE_NAMES["ifrs"], "added": added, "errors": errs[:10],
                      "ok": added > 0 or not errs, "checked_at": now_iso()}

    # ---------- 修正只能猜测日期的 IFRS 条目 ----------
    fixed = 0
    need = [x for x in items.values() if x["source"] == "ifrs" and (
        x.get("date_guess") or (x.get("date", "").endswith("-01") and not x.get("date_checked")))]
    for it in need[:80]:
        try:
            art = ifrs.parse_article(ifrs.get(it["url"]), it["url"])
            it["date"] = art["date"]
            it["date_checked"] = True
            if not art.get("date_guess"):
                it.pop("date_guess", None)
                fixed += 1
            texts[it["id"]] = art["text"]
            do_auto(it, art["text"])
            if not it.get("ai"):
                try_ai(it, art["text"])
        except Exception as e:  # noqa: BLE001
            print("  日期修正失败", it["url"], e)
    if fixed:
        print(f"修正了 {fixed} 条 IFRS 日期")

    # ---------- 补做自动中文信息（以前抓的、或上次翻译失败的） ----------
    AUTO_VER = 3   # 规则改了就加 1，已有条目会重新提取一次
    need = [x for x in items.values() if x["id"] not in texts and (
        "auto" not in x or (x.get("auto") or {}).get("v", 1) < AUTO_VER
        or (x["source"] == "ifrs" and not (x.get("auto") or {}).get("title_zh"))
        or (x["source"] == "ifrs" and not (x.get("auto") or {}).get("summary")))]
    need.sort(key=lambda x: x.get("date") or "", reverse=True)
    for it in need[:150]:
        try:
            if it["source"] in ("mof", "csrc"):
                text, att = (mof if it["source"] == "mof" else csrc).fetch_detail(it)
                it.setdefault("attachments", att)
            else:
                text = ifrs.parse_article(ifrs.get(it["url"]), it["url"])["text"]
            texts[it["id"]] = text
            do_auto(it, text)
        except Exception as e:  # noqa: BLE001
            print("  补做失败", it["url"], e)

    # ---------- 补做以前没做成的 AI 摘要 ----------
    pending = [it for it in items.values() if not it.get("ai") and it["id"] not in texts]
    pending.sort(key=lambda x: x.get("date") or "", reverse=True)
    for it in pending:
        if ai_budget[0] <= 0 or not summarize.backend():
            break
        try:
            if it["source"] in ("mof", "csrc"):
                text, _ = (mof if it["source"] == "mof" else csrc).fetch_detail(it)
            else:
                text = ifrs.parse_article(ifrs.get(it["url"]), it["url"])["text"]
        except Exception:  # noqa: BLE001
            text = ""
        try_ai(it, text)

    # ---------- 写文件 ----------
    for k, v in status.items():
        prev = db["sources"].get(k, {})
        v["last_success"] = v["checked_at"] if v["ok"] else prev.get("last_success")
    db["sources"].update(status)
    db["auto_status"] = dict(auto.status, checked_at=now_iso())
    db["ai_status"] = {"backend": summarize.backend(), "checked_at": now_iso(),
                       "made": MAX_AI - ai_budget[0] if not ai_note and ai_budget[0] > 0 else None,
                       "note": ai_note[:1], "errors": ai_errors[:3]}
    all_items = sorted(items.values(), key=lambda x: (x.get("date") or "", x["fetched_at"]), reverse=True)
    db["items"] = all_items[:MAX_ITEMS]
    db["updated_at"] = now_iso()

    DATA.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    DATA.write_text(body, "utf-8")
    ver = hashlib.sha1(json.dumps(db["items"], ensure_ascii=False).encode()).hexdigest()[:12]
    META.write_text(json.dumps({"updated_at": db["updated_at"], "count": len(db["items"]), "version": ver,
                                "sources": {k: {"ok": v["ok"], "last_success": v.get("last_success")}
                                            for k, v in db["sources"].items()}},
                               ensure_ascii=False), "utf-8")

    for k, v in status.items():
        print(f"[{v['name']}] 新增 {v['added']} 条，错误 {len(v['errors'])} 个")
        for e in v["errors"][:5]:
            print("   ", e.splitlines()[0])
    print(f"共 {len(db['items'])} 条，本次生成摘要 {MAX_AI - ai_budget[0] if ai_budget[0] > 0 else '若干'} 条（AI：{summarize.backend() or '未启用'}）")

    for line in status.get("csrc", {}).get("stats", []):
        print("   证监会", line)
    if all(not v["ok"] for v in status.values()):
        print("所有来源都抓取失败，请检查网站是否改版或屏蔽了 GitHub 的服务器")
        sys.exit(1)


if __name__ == "__main__":
    main()
