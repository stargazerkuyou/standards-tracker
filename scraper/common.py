"""公共工具：HTTP 请求、日期解析、条目结构、分类规则。"""
import hashlib
import re
import time
from datetime import datetime, timezone

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})


def get(url, timeout=30, retries=3):
    """带重试的 GET，返回解码后的文本。"""
    last = None
    for i in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def make_id(url):
    u = re.sub(r"^https?://", "", url.strip()).rstrip("/")
    return hashlib.sha1(u.encode("utf-8")).hexdigest()[:12]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


EN_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def parse_date(text):
    """从文本中找出第一个日期，返回 YYYY-MM-DD；找不到返回 None。"""
    if not text:
        return None
    m = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", text)
    if m and m.group(2).lower() in EN_MONTHS:
        return f"{int(m.group(3)):04d}-{EN_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})", text)
    if m and m.group(1).lower() in EN_MONTHS:
        return f"{int(m.group(3)):04d}-{EN_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


# ---------- 规则分类（AI 摘要会再校正一次） ----------

def guess_type(title):
    t = title
    tl = title.lower()
    if "征求意见" in t or "exposure draft" in tl or "consults" in tl or "consultation" in tl \
            or "seeks" in tl or "request for information" in tl or "proposes" in tl or "征询" in t:
        return "征求意见"
    if "解释第" in t or "interpretation" in tl or "agenda decision" in tl or "ifric" in tl:
        return "解释"
    if "实施问答" in t or "应用指南" in t or "解读" in t or "educational" in tl:
        return "解读指引"
    if re.search(r"印发.*(准则|规定|制度)", t) or re.search(r"\bissues?\b", tl) \
            or "amendments" in tl or "修订" in t:
        return "准则发布"
    if "decision" in tl or "update" in tl or "meeting" in tl or "会议" in t:
        return "会议决定"
    return "动态"


def guess_framework(title, default):
    t = title
    tl = title.lower()
    if "可持续" in t or "issb" in tl or "sustainability" in tl or re.search(r"ifrs s[12]\b", tl) \
            or "nature-related" in tl or "climate" in tl or "气候" in t:
        return "可持续"
    if "审计" in t or "注册会计师" in t or "audit" in tl or "iaasb" in tl:
        return "监管"
    return default


STD_PATTERNS = [
    (r"IFRS\s?S\s?([12])\b", "IFRS S{}"),
    (r"IFRS\s?(\d{1,2})\b", "IFRS {}"),
    (r"IAS\s?(\d{1,2})\b", "IAS {}"),
    (r"IFRIC\s?(\d{1,2})\b", "IFRIC {}"),
    (r"企业会计准则第\s?(\d{1,2})\s?号", "CAS {}"),
    (r"企业会计准则解释第\s?(\d{1,2})\s?号", "CAS 解释{}"),
]


def find_standards(text):
    found = []
    for pat, fmt in STD_PATTERNS:
        for m in re.finditer(pat, text or "", re.I):
            s = fmt.format(m.group(1))
            if s not in found:
                found.append(s)
    return found[:8]


def new_item(*, url, title, source, framework, date=None, kind=None, section=None):
    return {
        "id": make_id(url),
        "url": url,
        "title": title.strip(),
        "source": source,          # mof / ifrs ...
        "section": section,        # 栏目
        "framework": framework,    # 中国准则 / IFRS / 可持续 / 监管
        "type": kind or guess_type(title),
        "date": date,
        "standards": find_standards(title),
        "fetched_at": now_iso(),
        "ai": None,                # AI 摘要，见 summarize.py
    }
