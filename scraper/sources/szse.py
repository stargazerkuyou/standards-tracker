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


CASE_SECTION = re.compile(r"[三四五]、\s*(?:典型)?(?:会计)?案例研究")
NEXT_SECTION = re.compile(r"^\s*[四五六]、\s*(?:会计|审计|政策)")
CASE_HEAD = re.compile(r"^\s*(?:（[一二三四五六七八九十]{1,3}）|\([一二三四五六七八九十]{1,3}\)|案例[一二三四五六七八九十\d]+[：:、]?|问题\s*\d+\s*[【\[]?)(.{4,60})$")


def case_headings(text, limit=8):
    """附件里「典型会计案例研究」部分的小标题，例如“（一）外购在研项目资本化的判断”。"""
    lines = (text or "").splitlines()
    starts = [i for i, l in enumerate(lines) if CASE_SECTION.search(l)]
    if not starts:
        return []
    # 第一次出现多半是目录，取最后一次（正文里的那个）
    out = []
    for line in lines[starts[-1] + 1:]:
        if NEXT_SECTION.match(line):
            break
        m = CASE_HEAD.match(line.strip())
        if m:
            h = re.sub(r"\s+", "", line.strip())
            h = re.sub(r"[.．…·]{3,}.*$", "", h).rstrip("。；;，,")
            if 6 <= len(h) and h not in out:
                out.append(h[:60])
        if len(out) >= limit:
            break
    return out
