"""中国证监会 www.csrc.gov.cn —— 只收会计监管相关内容

证监会的栏目列表是网页脚本加载的，背后有一个 JSON 接口：
  /searchList/{频道ID}?_isAgg=true&_isJson=true&_pageSize=20&_template=index&page=1
频道 ID 可以直接写死，也可以从栏目网页的 <meta name="channelid"> 里读出来。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import session, get, new_item, parse_date, guess_type

BASE = "https://www.csrc.gov.cn"
HEAD = {"Referer": BASE + "/csrc/index.shtml", "X-Requested-With": "XMLHttpRequest"}

# (栏目名, 频道ID 或 栏目网址, 标题必须匹配的关键词)
CHANNELS = [
    ("监管规则适用指引", "a646cc4ea60542d081bd38eab9494c92", re.compile(r"会计")),
    ("证监会要闻", BASE + "/csrc/c100028/common_list.shtml",
     re.compile(r"会计监管|会计类|年报.{0,6}会计|会计.{0,4}(问题|提示|报告)|财务信息披露|财务造假")),
    ("新闻发布", BASE + "/csrc/c100029/common_list.shtml",
     re.compile(r"会计监管|会计类|年报.{0,6}会计|会计.{0,4}(问题|提示|报告)")),
]
ATTACH_RE = re.compile(r"\.(pdf|docx?|xlsx?|wps|zip|rar)$", re.I)


def channel_id(ref):
    if not ref.startswith("http"):
        return ref
    html = get(ref, timeout=60)
    m = re.search(r'channel[_-]?id[^0-9a-f<>]{0,40}([0-9a-f]{32})', html, re.I) \
        or re.search(r'([0-9a-f]{32})[^<>]{0,40}channel[_-]?id', html, re.I) \
        or re.search(r'searchList/([0-9a-f]{32})', html)
    if not m:
        hint = re.findall(r'<meta[^>]{0,120}>', html)[:6]
        raise RuntimeError("栏目页里找不到频道编号；页面 meta：" + " | ".join(hint)[:300])
    return m.group(1)


def _find_results(obj):
    """接口结构可能变化：递归找出“带 title 和 url 的字典列表”。"""
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj) and any("title" in x and "url" in x for x in obj):
            return obj
        for x in obj:
            r = _find_results(x)
            if r:
                return r
    elif isinstance(obj, dict):
        for k in ("results", "data", "list", "rows"):
            if k in obj:
                r = _find_results(obj[k])
                if r:
                    return r
        for v in obj.values():
            r = _find_results(v)
            if r:
                return r
    return None


def _date_of(rec):
    for k in ("publishedTimeStr", "publishedTime", "pubDate", "publishTime", "createTime", "date", "time"):
        v = rec.get(k)
        if v:
            if isinstance(v, (int, float)) and v > 1e11:   # 毫秒时间戳
                from datetime import datetime, timezone
                return datetime.fromtimestamp(v / 1000, timezone.utc).strftime("%Y-%m-%d")
            d = parse_date(str(v))
            if d:
                return d
    return None


def search_list(cid, page_size=20):
    params = {"_isAgg": "true", "_isJson": "true", "_pageSize": page_size, "_template": "index",
              "_rangeTimeGte": "", "_channelName": "", "page": 1}
    last = None
    for base in (BASE, "http://www.csrc.gov.cn"):          # https 不通就试 http
        for _ in range(2):
            try:
                r = session.get(f"{base}/searchList/{cid}", headers=HEAD, timeout=(20, 90), params=params)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # noqa: BLE001
                last = e
                data = None
        if data is not None:
            break
    if data is None:
        raise last
    rows = _find_results(data) or []
    out = []
    for rec in rows:
        title = re.sub(r"<[^>]+>", "", str(rec.get("title") or "")).strip()
        link = urljoin(BASE, str(rec.get("url") or ""))
        if title and link:
            out.append((title, link, _date_of(rec)))
    return out


def fetch_list():
    items, errors, stats = [], [], []
    for name, ref, kw in CHANNELS:
        try:
            rows = search_list(channel_id(ref))
            kept = 0
            for title, link, date in rows:
                if not kw.search(title):
                    continue
                kind = "解读指引" if re.search(r"指引|提示|问答|报告", title) else guess_type(title)
                items.append(new_item(url=link, title=title, source="csrc", framework="监管",
                                      date=date, kind=kind, section=name))
                kept += 1
            stats.append(f"{name}: 列表 {len(rows)} 条，相关 {kept} 条")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {str(e)[:200]}")
    uniq = {}
    for it in items:
        uniq.setdefault(it["id"], it)
    return list(uniq.values()), errors, stats


def fetch_detail(item):
    html = get(item["url"])
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    body = None
    for sel in ["div.detail-news", "div.content", "#ContentRegion", "div.TRS_Editor", "div.article"]:
        body = soup.select_one(sel)
        if body and len(body.get_text(strip=True)) > 50:
            break
        body = None
    if body is None:
        divs = soup.find_all("div")
        body = max(divs, key=lambda d: len(d.get_text(strip=True)), default=soup)
    if not item.get("date"):
        item["date"] = parse_date(soup.get_text(" ", strip=True)[:3000])
    att = []
    for a in soup.find_all("a", href=True):
        href = urljoin(item["url"], a["href"].strip())
        if ATTACH_RE.search(href) and not any(x["url"] == href for x in att):
            att.append({"name": a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1], "url": href})
    text = re.sub(r"\n\s*\n+", "\n", body.get_text("\n", strip=True))
    return text, att
