"""IFRS 基金会（IASB / IFRS 解释委员会 / ISSB）www.ifrs.org

新闻列表页是 JavaScript 动态加载的，抓不到；但网站的 sitemap.xml 会列出所有新闻网址
（形如 /news-and-events/news/2026/11/slug/），所以：读 sitemap → 找出新网址 → 逐篇抓详情页。
"""
import re
from datetime import date

from bs4 import BeautifulSoup

from common import get, new_item, parse_date, guess_framework, guess_type, find_standards

SITEMAP = "https://www.ifrs.org/sitemap.xml"
NEWS_RE = re.compile(r"https://www\.ifrs\.org/news-and-events/news/(20\d{2})/(\d{2})/[^<\s]+?/?(?=<|\s|$)")


def list_news_urls(xml, months_back):
    today = date.today()
    cutoff = (today.year * 12 + today.month) - months_back
    urls = []
    for m in NEWS_RE.finditer(xml):
        y, mo = int(m.group(1)), int(m.group(2))
        if y * 12 + mo > cutoff:
            u = m.group(0)
            if not u.endswith("/"):
                u += "/"
            if u not in urls:
                urls.append(u)
    return urls


def parse_article(html, url):
    soup = BeautifulSoup(html, "lxml")

    def meta(*names):
        for n in names:
            t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if t and t.get("content"):
                return t["content"].strip()
        return ""

    title = meta("og:title")
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else url)
    title = re.sub(r"\s*\|\s*IFRS.*$", "", title).strip()
    keywords = [k.strip() for k in meta("keywords").split(",") if k.strip()]

    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in main.find_all(["p", "li", "h2", "h3"])]
    paras = [p for p in paras if len(p) > 30 and "cookie" not in p.lower()]
    text = "\n".join(paras)

    d = parse_date(meta("article:published_time", "date", "publishdate", "dc.date"))
    if not d:
        top = main.get_text(" ", strip=True)[:3000]
        d = parse_date(top)
    if not d:
        m = re.search(r"/news/(20\d{2})/(\d{2})/", url)
        d = f"{m.group(1)}-{m.group(2)}-01"

    label = next((k for k in keywords if k.lower() in
                  ("press release", "news", "news article", "statement", "speech", "podcast", "webcast")), "")
    return {"title": title, "date": d, "keywords": keywords, "label": label, "text": text}


def build_item(url, art):
    kw = " ".join(art["keywords"])
    fw = guess_framework(art["title"] + " " + kw, "IFRS")
    if "International Sustainability Standards Board" in kw:
        fw = "可持续"
    it = new_item(url=url, title=art["title"], source="ifrs", framework=fw, date=art["date"],
                  section=art["label"] or "News", kind=guess_type(art["title"]))
    stds = find_standards(art["title"] + " " + kw)
    it["standards"] = stds
    it["title_en"] = art["title"]
    return it


def fetch_new(known_ids, months_back, limit):
    """返回 (新条目列表[(item, 正文)], 错误列表)。"""
    from common import make_id
    errors = []
    try:
        xml = get(SITEMAP, timeout=60)
    except Exception as e:  # noqa: BLE001
        return [], [f"sitemap: {e}"]
    urls = [u for u in list_news_urls(xml, months_back) if make_id(u) not in known_ids]
    # sitemap 大致按时间顺序排列，新的在后面
    urls = urls[::-1][:limit]
    out = []
    for u in urls:
        try:
            art = parse_article(get(u), u)
            out.append((build_item(u, art), art["text"]))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{u}: {e}")
    return out, errors
