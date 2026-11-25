"""不用 AI 的“自动中文信息”：规则提取摘要和日期 + 免费机器翻译。

结果存在 item["auto"]：
  title_zh          中文标题（IFRS 机器翻译；财政部原本就是中文）
  summary           摘要（IFRS：导语翻译；财政部：正文开头的要点句）
  comment_deadline  意见截止日 YYYY-MM-DD
  effective_date    生效日（YYYY-MM-DD 或原文描述）
  translated_by     用了哪个翻译来源
"""
import re
import time

import requests

from common import parse_date

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
status = {"ok": 0, "fail": 0, "last_error": None, "engine": None}

# 机器翻译后的术语纠正（左边是常见误译，右边是规范译法）
GLOSSARY = [
    (r"国际会计准则委员会|国际会计标准委员会|国际会计准则局", "国际会计准则理事会"),
    (r"国际可持续发展标准委员会|国际可持续发展准则委员会|国际可持续标准委员会|国际可持续发展准则理事会", "国际可持续准则理事会"),
    (r"国际财务报告准则基金会|IFRS基金会", "IFRS 基金会"),
    (r"国际财务报告解释委员会|IFRS解释委员会|国际财务报告准则解释委员会", "IFRS 解释委员会"),
    (r"实施后审查|实施后复核|实施后评审", "实施后审议"),
    (r"暴露草案|曝光草案|征求意见草案", "征求意见稿"),
    (r"征求意见函", "意见征询函"),
    (r"租约", "租赁"),
    (r"保险合约", "保险合同"),
    (r"财务报表的呈报和披露|财务报表的列报与披露|财务报表的呈现和披露", "财务报表的列报和披露"),
    (r"与客户签订合同的收入|客户合同收入", "与客户之间的合同产生的收入"),
    (r"套期会计|对冲会计", "套期会计"),
    (r"(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", r"\1年\2月\3日"),
]


def fix_terms(s):
    for a, b in GLOSSARY:
        s = re.sub(a, b, s)
    return s.strip()


def _gtx(text):
    r = requests.get("https://translate.googleapis.com/translate_a/single", headers=UA, timeout=30,
                     params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text})
    r.raise_for_status()
    return "".join(seg[0] for seg in r.json()[0] if seg and seg[0])


def _mymemory(text):
    out = []
    for chunk in re.findall(r".{1,450}(?:[.!?;]\s|$)", text, re.S) or [text[:450]]:
        r = requests.get("https://api.mymemory.translated.net/get", headers=UA, timeout=30,
                         params={"q": chunk, "langpair": "en|zh-CN"})
        r.raise_for_status()
        d = r.json()
        if int(d.get("responseStatus", 200)) != 200:
            raise RuntimeError(d.get("responseDetails", "MyMemory 出错"))
        out.append(d["responseData"]["translatedText"])
    return "".join(out)


ENGINES = [("谷歌翻译", _gtx), ("MyMemory", _mymemory)]
_dead = set()


def translate(text):
    text = (text or "").strip()
    if not text:
        return None
    for name, fn in ENGINES:
        if name in _dead:
            continue
        try:
            zh = fn(text[:1800])
            if zh and re.search(r"[一-鿿]", zh):
                status["ok"] += 1
                status["engine"] = name
                time.sleep(0.8)
                return fix_terms(zh)
            raise RuntimeError("返回内容不是中文")
        except Exception as e:  # noqa: BLE001
            status["fail"] += 1
            status["last_error"] = f"{name}: {str(e)[:200]}"
            if status["fail"] >= 3 and status["ok"] == 0:
                _dead.add(name)   # 连续失败就别再试这个来源了
    return None


# ---------------- 规则提取 ----------------

def _iso_or_text(s):
    d = parse_date(s)
    return d or s


def extract_dates(text):
    t = text or ""
    out = {"comment_deadline": None, "effective_date": None}
    # 中文：请于2026年10月11日前将意见反馈……
    m = re.search(r"(?:于|在)\s*(20\d{2}年\d{1,2}月\d{1,2}日)\s*(?:前|之前)", t)
    if m:
        out["comment_deadline"] = parse_date(m.group(1))
    m = re.search(r"自\s*(20\d{2}年\d{1,2}月\d{1,2}日)\s*起(?:施行|执行|实施|生效)", t)
    if m:
        out["effective_date"] = parse_date(m.group(1))
    # 英文
    date_en = r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})"
    m = re.search(r"(?:comment|feedback|respond|responses?)[^.]{0,80}?(?:by|until|before|deadline(?: is)?|closes?(?: on)?)\s+" + date_en, t, re.I)
    if m:
        out["comment_deadline"] = parse_date(m.group(1))
    m = re.search(r"effective for annual (?:reporting )?periods beginning on or after\s+" + date_en, t, re.I)
    if m:
        out["effective_date"] = "{}（年度报告期间开始日在此之后适用）".format(parse_date(m.group(1)))
    elif re.search(r"effective (?:from|on)\s+" + date_en, t, re.I):
        out["effective_date"] = parse_date(re.search(r"effective (?:from|on)\s+" + date_en, t, re.I).group(1))
    return out


SKIP_LINE = re.compile(r"^(各|国务院|有关|财政部各地|新疆|附件|联\s*系|电\s*话|电子邮箱|通讯地址|地\s*址|邮\s*编)|[：:]$")


def mof_summary(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    picked = []
    for l in lines:
        if SKIP_LINE.search(l) or len(l) < 15:
            continue
        picked.append(l)
        if sum(len(x) for x in picked) > 120:
            break
    s = "".join(picked)
    return (s[:220] + "……") if len(s) > 220 else (s or None)


def ifrs_lead(text):
    paras = [p.strip() for p in (text or "").splitlines() if len(p.strip()) > 60]
    paras = [p for p in paras if not re.match(r"^\d{1,2}\s+\w+\s+20\d{2}$", p)]
    lead = " ".join(paras[:2])
    return lead[:700]


def build(item, text):
    dates = extract_dates(text)
    auto = {"comment_deadline": dates["comment_deadline"], "effective_date": dates["effective_date"]}
    if item["source"] == "ifrs":
        auto["title_zh"] = translate(item.get("title_en") or item["title"])
        lead = ifrs_lead(text)
        auto["summary"] = translate(lead) if lead else None
        auto["translated_by"] = status["engine"] if auto["title_zh"] else None
    else:
        auto["summary"] = mof_summary(text)
    return auto
