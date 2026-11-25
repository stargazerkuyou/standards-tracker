"""给每条动态生成中文摘要。每条只生成一次，结果存进 data.json。

两种 AI 来源，自动选择：
1. 设置了 ANTHROPIC_API_KEY → 用 Claude（付费，质量更好；可选 ANTHROPIC_MODEL）
2. 否则用 GitHub Models（免费，有每日次数限制；在 Actions 里用自带的 GITHUB_TOKEN，无需任何密钥；
   可在仓库 Variables 里设 GITHUB_MODEL 换模型）
"""
import json
import os
import re

import requests

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-5-5"
GH_API = "https://models.github.ai/inference/chat/completions"
GH_MODEL = os.environ.get("GITHUB_MODEL") or "openai/gpt-4.1-mini"


class RateLimited(Exception):
    """免费额度用完了，今天先停，明天自动补。"""


def backend():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GITHUB_TOKEN"):
        return "github"
    return None
TYPES = ["准则发布", "解释", "征求意见", "解读指引", "会议决定", "动态"]

SYSTEM = """你是一名资深会计准则研究员，帮一位在企业做财务实务工作的中国会计人员快速判断准则动态。
只根据提供的原文作答，原文没写的信息填 null，绝不编造日期、文号或准则编号。
只输出一个 JSON 对象，不要输出任何其他文字。"""

PROMPT = """请阅读下面这条{source}动态，输出 JSON，字段如下：
{{
  "title_zh": "中文标题（原文是中文就保持原样；英文就译成规范的中文会计术语）",
  "summary": "2~4 句中文概述：发生了什么、为什么重要",
  "changes": ["具体改了什么 / 提出了什么，每条一句，最多 5 条；纯新闻活动类可为空数组"],
  "effective_date": "生效日期，YYYY-MM-DD；若只有描述（如'2027年1月1日或之后开始的年度期间'）就写原话；没有则 null",
  "comment_deadline": "征求意见截止日期 YYYY-MM-DD，没有则 null",
  "affects": "主要影响哪类企业或业务（如'有大量租赁的零售企业'），没有明显影响则 null",
  "standards": [{{"cas": "对应的中国企业会计准则，如 'CAS 21 租赁'，不确定则 null", "ifrs": "对应的 IFRS/IAS，如 'IFRS 16 租赁'，不确定则 null"}}],
  "type": "从 {types} 中选一个",
  "importance": "高 / 中 / 低",
  "importance_reason": "一句话说明重要度理由"
}}
重要度标准（站在企业财务实务角度）：
- 高：新准则、准则修订、准则解释、正式发布的征求意见稿，会改变报表确认、计量、列报或披露
- 中：理事会会议的暂定决定、项目进展、实施指引、执行问答、监管提示
- 低：人事任免、会议活动、播客、预算、一般性新闻

来源：{source}
栏目：{section}
标题：{title}
日期：{date}
网址：{url}
正文（可能被截断）：
{text}
"""


def summarize(item, text):
    be = backend()
    if not be:
        return None
    source = {"mof": "财政部会计司", "ifrs": "IFRS 基金会（IASB/ISSB）"}.get(item["source"], item["source"])
    limit = 9000 if be == "anthropic" else 4500   # 免费模型单次输入有长度限制
    prompt = PROMPT.format(source=source, section=item.get("section") or "", title=item["title"],
                           date=item.get("date") or "", url=item["url"], types="/".join(TYPES),
                           text=(text or "")[:limit])
    if be == "anthropic":
        r = requests.post(API, timeout=120, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
            "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 1200, "system": SYSTEM,
                  "messages": [{"role": "user", "content": prompt}]})
        if r.status_code == 429:
            raise RateLimited("Claude API 限流")
        if r.status_code >= 400:
            raise RuntimeError(f"Claude API HTTP {r.status_code}: {r.text[:300]}")
        out = "".join(b.get("text", "") for b in r.json().get("content", []))
        model = MODEL
    else:
        r = requests.post(GH_API, timeout=120, headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Content-Type": "application/json"},
            json={"model": GH_MODEL, "max_tokens": 1200, "temperature": 0.2,
                  "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
        if r.status_code == 429:
            raise RateLimited("GitHub Models 今日免费额度已用完")
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub Models HTTP {r.status_code}: {r.text[:300]}")
        out = r.json()["choices"][0]["message"]["content"]
        model = GH_MODEL
    data = parse_json(out)
    data["model"] = model
    return data


def parse_json(out):
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise ValueError("AI 没有返回 JSON")
    data = json.loads(m.group(0))
    if data.get("type") not in TYPES:
        data["type"] = None
    if data.get("importance") not in ("高", "中", "低"):
        data["importance"] = "中"
    data["changes"] = [c for c in (data.get("changes") or []) if isinstance(c, str)][:5]
    data["standards"] = [s for s in (data.get("standards") or []) if isinstance(s, dict)][:6]
    return data
