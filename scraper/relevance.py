"""只保留“准则相关”的内容；不相关的直接不抓。

用户要的：准则、解释、应用指南、实施问答、案例解析、会计监管动态/报告/规则、
          IASB/ISSB 每月会议决定、可持续披露、XBRL 分类标准。
不要的：  人事与机构治理、注册会计师行业、播客/演讲/论坛/研讨会、国际合作与趋同、
          非企业会计（行政事业单位、社保基金、管理会计、考试等）、规划和综述类文章。

规则：先看“排除词”，命中就丢；再看“保留词”，命中才留；都不命中也丢。
想调整，改下面的词表即可（正则表达式）。
"""
import re

# ---------------- 财政部（中文标题） ----------------
MOF_DROP = re.compile(
    r"注册会计师|会计师事务所|事务所|鉴证|审计|"
    r"行政事业单位|政府会计|社会保险基金|预算|财政总|彩票|"
    r"考试|大纲|管理会计|会计人员|会计职业道德|总会计师|代理记账|会计档案|"
    r"一带一路|论坛|中日韩|趋同|合作|"
    r"规划|数智化|信息化|新闻发布会|文字实录|二十载|周年|综述|座谈|培训|表彰|"
    r"内部控制")
MOF_KEEP = re.compile(
    r"企业会计准则|会计准则|准则解释|解释第|应用指南|实施问答|案例|会计处理|暂行规定|会计科目|"
    r"可持续披露|国际财务报告准则|国际会计准则理事会|国际可持续准则理事会|"
    r"实施情况分析报告|年报工作|会计信息质量|会计监管|"
    r"XBRL|扩展分类|通用分类标准")

# ---------------- IFRS（英文标题） ----------------
IFRS_DROP = re.compile(
    r"appoint|re-?appoint|\bchair\b|vice-chair|trustee|nominat|\bjoins?\b|new members?|"
    r"budget|five-year plan|meet the|senior advis|managing director|location|office in|"
    r"speech|webinar|webcast|\blive\b|conference|forum|call for papers|training|"
    r"takeaways|highlights|preview|implementation insights|advisory group|"
    r"strategic priorit|recruit|vacanc|job|career", re.I)
IFRS_KEEP = re.compile(
    r"\bissues?\b|publish|amend|exposure draft|propos|consult|seeks|feedback|request for information|"
    r"post-implementation review|\bPIR\b|agenda decision|IFRIC|Interpretations Committee|"
    r"decision|\bupdates?\b|taxonom|\bIFRS\s?S?\d|\bIAS\s?\d|standard|disclosure|effective|"
    r"comment", re.I)

# 纯播客（不是“月度 Update + 播客”）也不要
PODCAST_ONLY = re.compile(r"podcast", re.I)
UPDATE = re.compile(r"\bupdate\b", re.I)


def keep(item):
    src = item.get("source")
    if src == "mof":
        t = item.get("title", "")
        if MOF_DROP.search(t):
            return False
        return bool(MOF_KEEP.search(t))
    if src == "ifrs":
        t = item.get("title_en") or item.get("title", "")
        if (item.get("section") or "").lower() in ("speech", "podcast", "webcast"):
            return False
        if IFRS_DROP.search(t):
            return False
        if PODCAST_ONLY.search(t) and not UPDATE.search(t):
            return False
        return bool(IFRS_KEEP.search(t))
    return True   # 证监会：抓取时已经按会计监管关键词筛过


# ---------------- 类型重新判断（比通用规则更准） ----------------

def classify(item):
    t = item.get("title_en") or item.get("title", "")
    tl = t.lower()
    if item.get("source") == "ifrs":
        if re.search(r"exposure draft|propos|consult|seeks|feedback|request for information|comment", tl):
            return "征求意见"
        if re.search(r"agenda decision|ifric|interpretations committee", tl):
            return "解释"
        if re.search(r"\bissues?\b|publish|amend", tl) and not re.search(r"update", tl):
            return "准则发布"
        if re.search(r"decision|update|meeting|post-implementation review", tl):
            return "会议决定"
        return "动态"
    if item.get("source") == "mof":
        if "征求意见" in t or "意见征询" in t:
            return "征求意见"
        if "解释第" in t:
            return "解释"
        if re.search(r"应用指南|实施问答|案例|解读|答记者问", t):
            return "解读指引"
        if re.search(r"印发|发布", t) and re.search(r"准则|规定|科目", t):
            return "准则发布"
        return "动态"
    return item.get("type") or "动态"
