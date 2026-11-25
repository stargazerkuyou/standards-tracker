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


def read(atts):
    """返回 (正文附件的文字, 附件名)；失败返回 ("", None)。"""
    a = main_attachment(atts)
    if not a:
        return "", None
    try:
        data = _download(a["url"])
        text = pdf_text(data) if a["url"].lower().endswith(".pdf") else docx_text(data)
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


HEAD_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]{1,3}、|第[一二三四五六七八九十]{1,3}[章条节部分]\s*|\d{1,2}-\d{1,2}\s+)(.{3,60})$")


def headings(text, limit=8):
    """附件里的一级标题，作为“要点”。例如“一、关于……的会计处理”。"""
    out = []
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        m = HEAD_RE.match(line)
        if not m:
            continue
        h = line
        # 标题被 PDF 拆成两行的，接上下一行
        if not re.search(r"[。？?：:）)]$", h) and len(h) < 30 and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and len(nxt) < 30 and not HEAD_RE.match(nxt) and not re.match(r"^[（(]", nxt):
                h += nxt
        h = re.sub(r"\s+", "", h)
        if h not in out and not re.search(r"附件|联系人|电话", h):
            out.append(h[:70])
        if len(out) >= limit:
            break
    return out
