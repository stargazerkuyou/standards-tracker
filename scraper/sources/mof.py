"""财政部会计司 kjs.mof.gov.cn

栏目列表页里的文章链接形如 ./202611/t20261118_4004909.htm，
列表上显示的日期是发布日期，链接里的日期是建稿日期（两者可能差几天），优先用列表日期。
注意：该站 https 会 302 跳到 http，所以直接用 http。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import get, new_item, parse_date, guess_framework

BASE = "http://kjs.mof.gov.cn/"
SECTIONS = {
    "zhengcefabu": "政策发布",
    "gongzuotongzhi": "工作通知",   # 征求意见函大多在这里
    "zhengcejiedu": "政策解读",
    "guojidongtai": "国际动态",
    "gongzuodongtai": "工作动态",
    "zt/kjzzss/sswd": "实施问答",      # 企业会计准则实施专题：各准则的实施问答
    "zt/kjzzss/srzzzq": "应用案例",    # 企业会计准则实施专题：应用案例
}
ARTICLE_RE = re.compile(r"/(\d{6})/t(\d{8})_\d+\.html?$")
ATTACH_RE = re.compile(r"\.(pdf|docx?|xlsx?|wps|ofd|zip|rar)$", re.I)

# 与会计准则工作无关、默认不收录的标题关键词
SKIP_WORDS = ["招聘", "党建", "党支部", "主题教育", "图片报道", "公示名单"]


def parse_list(html, page_url, section_name):
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"].strip())
        m = ARTICLE_RE.search(href)
        if not m or href in seen:
            continue
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        title = re.sub(r"^\s*问[：:]\s*", "", title)
        if len(title) < 6 or any(w in title for w in SKIP_WORDS) or title in ("更多", "更多>>", "更多> >"):
            continue
        seen.add(href)
        # 列表里显示的日期通常在同一个 <li>/<tr> 里
        date = None
        node = a
        for _ in range(3):
            node = node.parent
            if node is None:
                break
            txt = node.get_text(" ", strip=True)
            if len(txt) > len(title) + 80:   # 已经大到包住多条了，别再往上找
                break
            date = parse_date(txt.replace(title, ""))
            if date:
                break
        if not date:
            d = m.group(2)
            date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        items.append(new_item(url=href, title=title, source="mof", framework=guess_framework(title, "中国准则"),
                              date=date, section=section_name))
    return items


def parse_article(html, url):
    """返回 (正文文本, 附件列表)。"""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    body = None
    for sel in ["div.TRS_Editor", "#Zoom", "div.my_doccontent", "div.content", "div.article"]:
        body = soup.select_one(sel)
        if body and len(body.get_text(strip=True)) > 50:
            break
        body = None
    if body is None:  # 兜底：取文字最多的 div
        divs = soup.find_all("div")
        body = max(divs, key=lambda d: len(d.get_text(strip=True)), default=soup)
    attachments = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].strip())
        if ATTACH_RE.search(href):
            name = a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]
            if not any(x["url"] == href for x in attachments):
                attachments.append({"name": name, "url": href})
    text = re.sub(r"\n\s*\n+", "\n", body.get_text("\n", strip=True))
    return text, attachments


def fetch_list():
    items = []
    errors = []
    for slug, name in SECTIONS.items():
        url = BASE + slug + "/"
        try:
            items += parse_list(get(url), url, name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    # 同一篇文章可能出现在多个栏目
    uniq = {}
    for it in items:
        uniq.setdefault(it["id"], it)
    return list(uniq.values()), errors


def fetch_detail(item):
    text, att = parse_article(get(item["url"]), item["url"])
    return text, att
