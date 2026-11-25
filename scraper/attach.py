"""读取附件（PDF / docx）里的文字：正文在附件里时，用来生成摘要、要点和日期。"""
import io
import re
import unicodedata

from common import session

MAX_BYTES = 25 * 1024 * 1024
DOC_HINT = re.compile(r"说明|起草|对照|反馈|意见表|回执|名单|英文", re.I)


def _download(url):
    r = session.get(url, timeout=(20, 120), stream=True)
    r.raise_for_status()
    buf = io.BytesIO()
    for chunk in r.iter_content(65536):
        buf.write(chunk)
        if buf.tell() > MAX_BYTES:
            raise RuntimeError("附件太大")
    return buf.getvalue()


def pdf_text(data, max_pages=12):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for p in reader.pages[:max_pages]:
        try:
            out.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(out)


def docx_text(data):
    import docx
    d = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs)


def main_attachment(atts):
    """挑“正文”那个附件：PDF/docx 优先，名字里带“说明/起草/英文”的放后面。"""
    cands = [a for a in atts or [] if re.search(r"\.(pdf|docx)$", a["url"], re.I)]
    cands.sort(key=lambda a: (bool(DOC_HINT.search(a.get("name", ""))), not a["url"].lower().endswith(".pdf")))
    return cands[0] if cands else None


def read(atts, max_pages=12):
    """返回 (正文附件的文字, 附件名)；失败返回 ("", None)。"""
    a = main_attachment(atts)
    if not a:
        return "", None
    try:
        data = _download(a["url"])
        text = pdf_text(data, max_pages) if a["url"].lower().endswith(".pdf") else docx_text(data)
    except Exception as e:  # noqa: BLE001
        print("  附件读取失败", a["url"], e)
        return "", None
    return clean(text), a.get("name")


# NFKC 处理不了的“部首补充”字符
RADICALS = str.maketrans({"\u2ec5": "见", "\u2ed3": "长", "\u2ed4": "门", "\u2ec9": "车", "\u2ec9": "车",
                          "\u2ee2": "马", "\u2ee9": "黄", "\u2edc": "飞", "\u2ede": "食", "\u2ec6": "角",
                          "\u2eda": "页", "\u2ee5": "鱼", "\u2ec1": "虎", "\u2ecf": "阝", "\u2ed6": "阝",
                          "\u2ebc": "月", "\u2ec3": "西", "\u2ec4": "西", "\u2ed8": "青", "\u2ee3": "骨"})


def clean(text):
    """PDF 抽出来的文字：康熙部首“⼀⽉⽇”等换成正常汉字，去掉汉字、数字之间多余的空格。"""
    text = unicodedata.normalize("NFKC", text or "").translate(RADICALS)
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"(?<=[一-鿿\d]) (?=[一-鿿])|(?<=[一-鿿]) (?=\d)", "", text)
    return text.strip()


HEAD_RE = re.compile(r"^\s*(?:([一二三四五六七八九十]{1,3})、|第[一二三四五六七八九十]{1,3}[章条节部分]\s*|(\d{1,2})\s*[-－]\s*(\d{1,2})\s*(?=[\u4e00-\u9fff]))(.{3,60})$")
BODY_START = re.compile(r"(该问题|本解释|本指引|根据|按照|依据|企业应|在实务中|实务中|《企业会计准则|\(以下|（以下)")
# 标题通常以这些词结尾；不是的话，多半是被 PDF 换行截断了，要接上下一行
COMPLETE_END = re.compile(r"(处理|列报|披露|确认|计量|判断|分类|条件|日期|问题|规定|要求|内容|背景|计划|类|方法|范围|"
                          r"定义|原则|安排|衔接|施行|核算|关系|影响|担保|保险|损益|费用|收入|补偿|补贴|事项|情形|认定)$")
LEADER = re.compile(r"[.．…·。\-－_]{3,}.*$")      # 目录里的“……2”页码


def _num_key(m):
    if m.group(2):
        return (int(m.group(2)), int(m.group(3)))
    cn = "一二三四五六七八九十"
    g = m.group(1)
    if g:
        v = 10 + (cn.index(g[-1]) + 1 if len(g) > 1 else 0) if g[0] == "十" else cn.index(g[0]) + 1
        return (0, v)
    return None


def headings(text, limit=10):
    """附件里的一级标题，作为“要点”。例如“一、关于……的会计处理”、“5-1 ……”。
    同一个编号出现多次（目录一遍、正文一遍）时，保留最完整的那个。"""
    found = {}          # 编号 -> 标题
    order = []
    seen_one = False
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        m = HEAD_RE.match(line)
        if not m:
            continue
        if m.group(1) == "一":
            if seen_one:                       # 编号重新从“一、”开始：已经进入下一级内容，停
                break
            seen_one = True
        h = LEADER.sub("", re.sub(r"\s+", "", line))
        if not COMPLETE_END.search(h) and i + 1 < len(lines):
            nxt = LEADER.sub("", re.sub(r"\s+", "", lines[i + 1]))
            if nxt and len(nxt) < 40 and not HEAD_RE.match(lines[i + 1].strip()) and not BODY_START.match(nxt):
                h += nxt
        cut = BODY_START.search(h, 6)          # 标题后面粘上了正文，截掉
        if cut:
            h = h[:cut.start()]
        h = LEADER.sub("", h).rstrip("，,。；;：:0123456789-－ ")
        if len(h) < 5 or re.search(r"附件|联系人|电话|\d{4,}", h):
            continue
        key = _num_key(m) or h
        if key not in found:
            order.append(key)
            found[key] = h[:60]
        elif len(h) > len(found[key]) and COMPLETE_END.search(h):
            found[key] = h[:60]
    if any(isinstance(k, tuple) and k[0] > 0 for k in order):     # 有“5-1”这种编号时，“一、”是下一级小标题，不要
        order = [k for k in order if isinstance(k, tuple) and k[0] > 0]
    keys = sorted(order, key=lambda k: k if isinstance(k, tuple) else (99, 0)) if all(isinstance(k, tuple) for k in order) else order
    return [found[k] for k in keys][:limit]
