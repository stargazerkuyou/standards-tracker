"""深圳证券交易所《会计监管动态》 smehome.szse.cn/trends/accounting_supervise/

栏目页是普通网页，文章链接形如 ./202608/t20260826_5601.html；
每期正文是 PDF/Word 附件，“要点”取附件里「典型会计案例研究」部分的案例标题。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import get, new_item, parse_date

LIST_URL = "https://smehome.szse.cn/trends/accounting_supervise/index.html"
ART_RE = re.compile(r"/trends/accounting_supervise/(\d{6})/t(\d{8})_\d+\.html?$")
ATTACH_RE = re.compile(r"\.(pdf|docx?|wps)$", re.I)


def parse_list(html, page_url=LIST_URL):
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"].strip())
        m = ART_RE.search(href)
        if not m or href in seen:
            continue
        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        title = re.sub(r"\s*20\d{2}-\d{2}-\d{2}\s*$", "", title)      # 链接文字末尾带的日期
        if "会计监管" not in title:
            continue
        seen.add(href)
        li = a.find_parent(["li", "tr", "dd"])
        date = parse_date(li.get_text(" ", strip=True).replace(title, "")) if li else None
        if not date:
            d = m.group(2)
            date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        out.append(new_item(url=href, title=title, source="szse", framework="监管", date=date,
                            kind="解读指引", section="会计监管动态"))
    return out


def fetch_list():
    return parse_list(get(LIST_URL, timeout=60)), []


def fetch_detail(item):
    html = get(item["url"], timeout=60)
    soup = BeautifulSoup(html, "lxml")
    att = []
    for a in soup.find_all("a", href=True):
        href = urljoin(item["url"], a["href"].strip())
        if ATTACH_RE.search(href) and not any(x["url"] == href for x in att):
            name = a.get_text(" ", strip=True) or item["title"]
            if not ATTACH_RE.search(name):
                name += "." + href.rsplit(".", 1)[-1]
            att.append({"name": name, "url": href})
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    divs = soup.find_all("div")
    body = max(divs, key=lambda d: len(d.get_text(strip=True)), default=soup)
    text = re.sub(r"\n\s*\n+", "\n", body.get_text("\n", strip=True))
    return text, att


CASE_SECTION = re.compile(r"^\s*[二三四五]、\s*(?:典型)?(?:会计)?案例(?:研究|分析)?\s*$")
NEXT_SECTION = re.compile(r"^\s*[三四五六七]、.*(?:资讯|政策|动态|通讯)")
PAGE_HEADER = re.compile(r"会计监管动态\s*20\d{2}\s*年")
CASE_HEAD = re.compile(r"^\s*(?:\([一二三四五六七八九十]{1,3}\)|案例[一二三四五六七八九十\d]{1,3}\s*[:：、]?|问题\s*\d+\s*[【\[]?)(.{4,70})$")


def case_headings(text, limit=12):
    """附件里「典型会计案例研究」部分的小标题，例如“(一)研发支出及无形资产相关问题”“案例一:关于外购在研专利技术的会计处理”。"""
    lines = [l.strip() for l in (text or "").splitlines()]
    starts = [i for i, l in enumerate(lines) if CASE_SECTION.match(l)]
    if not starts:
        return []
    out = []
    for i in range(starts[-1] + 1, len(lines)):     # 第一次出现多半是目录，取正文里那一次
        line = lines[i]
        if NEXT_SECTION.match(line):
            break
        if PAGE_HEADER.search(line):
            continue
        m = CASE_HEAD.match(line)
        if not m:
            continue
        is_case = line.startswith(("案例", "问题"))
        h = re.sub(r"\s+", "", line)
        # “(一)”开头的只要分组标题（如“(一)收入相关问题”），不要案例里引用的准则条文
        if not is_case and not re.search(r"问题$", h):
            continue
        # 标题被换行截断：下一行很短且不是新标题，就接上
        if not re.search(r"(问题|处理|判断|影响|确认|计量|列报|披露|识别|分类|核算)$", h) and i + 1 < len(lines):
            nxt = re.sub(r"\s+", "", lines[i + 1])
            if nxt and len(nxt) < 30 and not CASE_HEAD.match(lines[i + 1]) and not PAGE_HEADER.search(nxt):
                h += nxt
        h = re.sub(r"[.．…·]{3,}.*$", "", h)
        h = re.sub(r"—\d+—", "", h)
        h = re.sub(r"\d\.案例及相关问题$", "", h).rstrip("。；;，,")
        if len(h) >= 6 and h not in out:
            out.append(h[:70])
        if len(out) >= limit:
            break
    return out


def summary(text):
    """每期导语里“会计案例方面，本期……”那句话最能说明这期讲了什么。"""
    t = re.sub(r"\s+", "", text or "")
    m = re.search(r"会计案例方面[，,](.{10,200}?。)", t)
    if m:
        return "会计案例方面，" + m.group(1)
    m = re.search(r"本期《深圳证券交易所会计监管动态》(.{10,200}?。)", t)
    return ("本期" + m.group(1)) if m else None
