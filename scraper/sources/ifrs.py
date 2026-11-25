"""IFRS 基金会（IASB / IFRS 解释委员会 / ISSB）www.ifrs.org

新闻列表页是 JavaScript 动态加载的，抓不到；但网站的 sitemap.xml 会列出所有新闻网址
（形如 /news-and-events/news/2026/11/slug/），所以：读 sitemap → 找出新网址 → 逐篇抓详情页。
"""
import re
from datetime import date

from bs4 import BeautifulSoup

from common import get, new_item, parse_date, guess_framework, guess_type, find_standards

SITEMAP = "https://www.ifrs.org/sitemap.xml"
BOILER = re.compile(r"cookie|skip to|sign in|log in|register|subscribe|follow us|copyright|all rights reserved|"
                    r"privacy|terms of use|share this|javascript|your browser", re.I)
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

    soup_text = soup.get_text(" ", strip=True)
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    def collect(root):
        out = []
        for el in root.find_all(["p", "li", "h2", "h3", "blockquote"]):
            t = el.get_text(" ", strip=True)
            if len(t) > 30 and not BOILER.search(t) and t not in out:
                out.append(t)
        return out

    main = soup.find("main") or soup.find("article") or soup.body or soup
    paras = collect(main)
    if sum(len(p) for p in paras) < 300 and soup.body:      # 正文不在 <main> 里时，扩大到整页
        paras = collect(soup.body)
    desc = meta("og:description", "description")
    if desc and len(desc) > 60 and desc not in paras:
        paras.insert(0, desc)
    text = "\n".join(paras)

    d, guessed = find_date(soup_text, url, meta("article:published_time", "date", "publishdate", "dc.date"))
    label = next((k for k in keywords if k.lower() in
                  ("press release", "news", "news article", "statement", "speech", "podcast", "webcast")), "")
    return {"title": title, "date": d, "date_guess": guessed, "keywords": keywords, "label": label, "text": text}


DATE_ANY = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})"
                      r"|(20\d{2})-(\d{2})-(\d{2})", re.I)


def find_date(text, url, meta_date=""):
    """页面里可能有很多日期（会议日期、生效日期……），取和网址年月最接近的那个。
    返回 (YYYY-MM-DD, 是否只是猜测)。"""
    m = re.search(r"/news/(20\d{2})/(\d{2})/", url)
    uy, um = int(m.group(1)), int(m.group(2))
    cands = []
    if meta_date:
        d = parse_date(meta_date)
        if d:
            cands.append(d)
    for mm in DATE_ANY.finditer(text or ""):
        d = parse_date(mm.group(0))
        if d:
            cands.append(d)
    for d in cands:   # 按出现顺序，第一个与网址同月（或前一个月）的就是发布日期
        y, mo = int(d[:4]), int(d[5:7])
        if (y * 12 + mo) in (uy * 12 + um, uy * 12 + um - 1):
            return d, False
    return f"{uy:04d}-{um:02d}-01", True


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
    if art.get("date_guess"):
        it["date_guess"] = True
    return it


def fetch_new(known_ids, months_back, limit):
    """返回 (新条目列表[(item, 正文)], 错误列表)。"""
    from common import make_id
    errors = []
    try:
        xml = get(SITEMAP, timeout=60)
    except Exception as e:  # noqa: BLE001
        return [], [f"sitemap: {e}"]
    from relevance import IFRS_DROP
    urls = [u for u in list_news_urls(xml, months_back) if make_id(u) not in known_ids
            and not IFRS_DROP.search(u.rstrip("/").rsplit("/", 1)[-1].replace("-", " "))]
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
