"""离线测试：用仿真网页跑通解析器和主流程（不联网、不调 AI）。
运行：python tests/test_offline.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))

import common  # noqa: E402
from sources import mof, ifrs, csrc, szse  # noqa: E402
import summarize  # noqa: E402
import fetch  # noqa: E402
import auto  # noqa: E402
auto.ENGINES[:] = [("假翻译", lambda t: "【译】国际会计准则委员会发布暴露草案：" + t[:20])]
auto.time.sleep = lambda s: None

MOF_LIST = """<html><body><div class="nav"><a href="/">首页</a><span>2017年11月21日</span></div>
<ul class="liBox">
<li><a href="./202611/t20261105_4004148.htm" title="关于印发《企业会计准则第30号——财务报表列报》的通知">关于印发《企业会计准则第30号——财务报表列报》的通知</a><span>2026-11-11</span></li>
<li><a href="./202611/t20261106_4004149.htm" title="关于印发《会计改革与发展“十五五”规划》的通知">关于印发《会计改革与发展“十五五”规划》的通知</a><span>2026-11-12</span></li>
<li><a href="./202609/t20260910_4001234.htm" title="关于征求《企业会计准则解释第22号(征求意见稿)》意见的函">关于征求《企业会计准则解释第22号(征求意见稿)》意见的函</a><span>2026-09-15</span></li>
<li><a href="./202610/t20261001_4000001.htm">财政部会计司党支部开展主题教育活动</a><span>2026-10-01</span></li>
</ul>
<div class="page"><a href="index_1.htm">下一页</a></div></body></html>"""

MOF_ARTICLE = """<html><body><div class="TRS_Editor"><p>各省、自治区、直辖市财政厅（局）：</p>
<p>为进一步规范有关业务的会计处理，我们起草了《企业会计准则解释第22号(征求意见稿)》。请于2026年10月11日前将意见反馈至财政部会计司。涉及《企业会计准则第21号——租赁》。</p></div>
<a href="./P020260910123.pdf">附件1.企业会计准则解释第22号(征求意见稿).pdf</a></body></html>"""

IFRS_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.ifrs.org/news-and-events/news/2019/05/old-story/</loc></url>
<url><loc>https://www.ifrs.org/news-and-events/news/{ym}/pir-ifrs-16-concludes-identifies-targeted-improvements/</loc></url>
<url><loc>https://www.ifrs.org/news-and-events/news/{ym}/meet-new-iasb-chair-sam-woods/</loc></url>
<url><loc>https://www.ifrs.org/projects/work-plan/</loc></url>
</urlset>"""

IFRS_ARTICLE = """<html><head><meta property="og:title" content="Post-implementation Review concludes IFRS 16 is working as intended but identifies areas for targeted improvements | IFRS Foundation">
<meta name="keywords" content="Post-implementation Review of IFRS 16 Leases, Press release, IFRS 16 Leases, International Accounting Standards Board, Media"></head>
<body><header>menu</header><main><h1>Post-implementation Review concludes IFRS 16 ...</h1><p>23 November 2026</p>
<p>The IASB has completed its Post-implementation Review of IFRS 16 Leases and concluded the Standard is working as intended.</p>
<p>We use cookies on ifrs.org to ensure the best user experience possible for everyone.</p></main></body></html>"""

IFRS_ARTICLE2 = """<html><head><meta property="og:title" content="Meet the new IASB Chair, Sam Woods"><meta name="keywords" content="News, International Accounting Standards Board"></head>
<body><main><p>20 November 2026</p><p>Sam Woods talks about his priorities for the International Accounting Standards Board.</p></main></body></html>"""


def fake_get_factory():
    from datetime import date
    ym = f"{date.today().year}/{date.today().month:02d}"

    def fake_get(url, timeout=30, retries=3):
        if url.endswith("sitemap.xml"):
            return IFRS_SITEMAP.format(ym=ym)
        if "ifrs.org" in url:
            return IFRS_ARTICLE if "pir-ifrs-16" in url else IFRS_ARTICLE2
        if url.rstrip("/").endswith(("zhengcefabu", "gongzuotongzhi")):
            return MOF_LIST
        if url.endswith("/"):
            return "<html><body>空栏目</body></html>"
        return MOF_ARTICLE
    return fake_get


def check(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        check.failed = True


check.failed = False


def test_parsers():
    print("解析器")
    items = mof.parse_list(MOF_LIST, "http://kjs.mof.gov.cn/zhengcefabu/", "政策发布")
    check(len(items) == 3, f"财政部列表解析出 3 条（跳过党建），实际 {len(items)}")
    check(items[0]["date"] == "2026-11-11", f"用列表显示日期而不是链接日期：{items[0]['date']}")
    import relevance
    check([relevance.keep(i) for i in items] == [True, False, True], "相关性：准则留下、规划去掉")
    qa = mof.parse_list("""<ul><li><a href="./gdzczzsswd/202504/t20250417_3962201.htm" title="问：甲公司已将研发样机支出费用化，此后销售样机时能否冲回研发费用？">问：甲公司已将研发样机支出费用化……</a><span>2025-04-17</span></li>
      <li><a href="./gdzczzsswd/">更多> ></a></li></ul>""", "http://kjs.mof.gov.cn/zt/kjzzss/sswd/", "实施问答")
    check(len(qa) == 1 and qa[0]["title"].startswith("甲公司已将研发样机") and relevance.keep(qa[0]) and relevance.classify(qa[0]) == "解读指引",
          f"实施问答：{[(q['title'], q['section']) for q in qa]}")
    check(items[0]["url"] == "http://kjs.mof.gov.cn/zhengcefabu/202611/t20261105_4004148.htm", "相对链接补全")
    check(items[2]["type"] == "征求意见", f"征求意见函分类：{items[2]['type']}")
    check("CAS 解释22" in items[2]["standards"], f"识别解释编号：{items[2]['standards']}")
    text, att = mof.parse_article(MOF_ARTICLE, "http://kjs.mof.gov.cn/zhengcefabu/202609/t.htm")
    check("2026年10月11日" in text and len(att) == 1, "正文和附件")
    art = ifrs.parse_article(IFRS_ARTICLE, "https://www.ifrs.org/news-and-events/news/2026/11/x/")
    check(art["title"].startswith("Post-implementation Review concludes") and "|" not in art["title"], "IFRS 标题去后缀")
    check(art["date"] == "2026-11-23", f"IFRS 日期：{art['date']}")
    check("cookie" not in art["text"].lower(), "过滤 cookie 提示")
    it = ifrs.build_item("https://www.ifrs.org/news-and-events/news/2026/11/x/", art)
    check(it["framework"] == "IFRS" and "IFRS 16" in it["standards"], f"IFRS 体系与准则：{it['framework']} {it['standards']}")
    check(common.parse_date("November 5, 2026") == "2026-11-05", "英文日期格式 2")
    check(common.guess_framework("ISSB consults on proposals for nature-related disclosures", "IFRS") == "可持续", "ISSB 归入可持续")
    ai = summarize.parse_json('好的：{"title_zh":"x","summary":"y","type":"乱写","importance":"很高","changes":["a",1],"standards":[{"cas":"CAS 21 租赁","ifrs":"IFRS 16 租赁"}]}')
    check(ai["type"] is None and ai["importance"] == "中" and ai["changes"] == ["a"], "AI 输出清洗")


def test_csrc():
    print("证监会")
    js = {"data": {"total": 3, "results": [
        {"title": "<em>监管规则适用指引——会计类第6号</em>", "url": "/csrc/c100038/c7700001/content.shtml", "publishedTimeStr": "2026-11-20 18:00:00"},
        {"title": "监管规则适用指引——发行类第9号", "url": "/csrc/c100038/c7700002/content.shtml", "publishedTimeStr": "2026-11-18"},
        {"title": "证监会发布2025年上市公司年报会计监管报告", "url": "https://www.csrc.gov.cn/csrc/c100028/c7700003/content.shtml", "publishedTime": 1793000000000}]}}
    check(len(csrc._find_results(js)) == 3, "找到结果列表")
    class R:
        def raise_for_status(self): pass
        def json(self): return js
    csrc.session.get = lambda *a, **k: R()
    rows = csrc.search_list("x")
    check(rows[0][0] == "监管规则适用指引——会计类第6号" and rows[0][2] == "2026-11-20" and rows[0][1].startswith("https://www.csrc.gov.cn/csrc/"), f"标题去标签、日期、网址：{rows[0]}")
    check(rows[2][2] and rows[2][2].startswith("2026"), f"毫秒时间戳日期：{rows[2][2]}")
    csrc.get = lambda url, **k: '<meta name="channelid" content="0123456789abcdef0123456789abcdef">'
    items, errs, stats = csrc.fetch_list()
    titles = [i["title"] for i in items]
    check("监管规则适用指引——发行类第9号" not in titles and "监管规则适用指引——会计类第6号" in titles, f"只收会计相关：{titles}")
    check(all(i["framework"] == "监管" for i in items) and not errs, f"分类=监管，无错误 {errs}")


def test_csrc_column():
    html = """<ul><li><a href="/csrc/c100029/cb7acea9e3b6c4c94bef46eb0ff3e5525/content.shtml" target="_blank">证监会发布2025年度上市公司年报会计监管报告</a><span>2026-08-15</span></li>
    <li><a href="/csrc/c100029/c7700009/content.shtml">证监会召开座谈会</a><span>2026-08-10</span></li></ul>"""
    rows = csrc.parse_column(html, "https://www.csrc.gov.cn/csrc/c100029/common_list.shtml")
    check(len(rows) == 2 and rows[0][2] == "2026-08-15" and rows[0][1].startswith("https://www.csrc.gov.cn/csrc/c100029/"), f"证监会栏目网页解析：{rows[:1]}")


def test_szse():
    print("深交所")
    html = """<ul><li><a href="./202608/t20260826_5601.html">《深圳证券交易所会计监管动态》（2026年第2期） 2026-08-26</a></li>
    <li><a href="./202604/t20260409_5581.html">《深圳证券交易所会计监管动态》（2026年第1期）</a><span>2026-04-09</span></li>
    <li><a href="/other/x.html">无关链接</a></li></ul>"""
    items = szse.parse_list(html, "https://smehome.szse.cn/trends/accounting_supervise/index.html")
    check(len(items) == 2 and items[0]["date"] == "2026-08-26" and items[0]["url"].endswith("/202608/t20260826_5601.html"), f"深交所列表：{[(i['title'], i['date']) for i in items]}")
    check(items[0]["framework"] == "监管" and items[0]["title"].endswith("（2026年第2期）"), f"分类=监管，标题去掉日期：{items[0]['title']}")
    t = """目录
一、深市会计审计监管通讯 3
三、典型会计案例研究 12
四、会计审计政策资讯 22
一、深市会计审计监管通讯
（一）审计评估机构纪律处分情况
三、典型会计案例研究
(一)研发支出及无形资产相关问题
案例一:关于外购在研专利技术的会计
处理
案例背景：A公司……
(一)与该无形资产有关的经济利益很可能流入企业
深圳证券交易所会计监管动态 2026 年第 2 期
案例二:关于委托开发软件摊销时点1.案例及相关问题
四、会计审计政策资讯
（一）财政部发布修订后财务报表列报准则"""
    hs = szse.case_headings(t)
    check(hs == ["(一)研发支出及无形资产相关问题", "案例一:关于外购在研专利技术的会计处理", "案例二:关于委托开发软件摊销时点"], f"案例标题：{hs}")
    sm = szse.summary("编者按……会计案例方面，本期主要围绕创新创业企业经常遇到的研发和股份支付相关会计处理，分析两组典型案例。会计审计政策资讯方面……")
    check(sm and sm.startswith("会计案例方面，本期主要围绕") and sm.endswith("典型案例。"), f"深交所摘要：{sm}")


def test_auto():
    print("自动中文信息")
    d = auto.extract_dates("请组织征求意见，并于2026年10月11日前将意见反馈至财政部会计司。本解释自2027年1月1日起施行。")
    check(d == {"comment_deadline": "2026-10-11", "effective_date": "2027-01-01"}, f"中文日期：{d}")
    d = auto.extract_dates("The amendments are effective for annual reporting periods beginning on or after 1 January 2027. Comments are requested by 30 March 2027.")
    check(d["comment_deadline"] == "2027-03-30" and d["effective_date"].startswith("2027-01-01"), f"英文日期：{d}")
    sm = auto.mof_summary("各省、自治区、直辖市财政厅（局）：\n为进一步规范有关业务的会计处理，我们起草了《企业会计准则解释第22号(征求意见稿)》。\n联系人：张三")
    check(sm.startswith("为进一步规范") and "联系人" not in sm, f"财政部摘要：{sm}")
    zh = auto.translate("IASB issues exposure draft")
    check("国际会计准则理事会" in zh and "征求意见稿" in zh, f"术语纠正：{zh}")


def test_main():
    print("主流程")
    fake = fake_get_factory()
    common.get = mof.get = ifrs.get = fake
    csrc.fetch_list = lambda: ([], [], ["测试: 列表 0 条，相关 0 条"])
    szse.fetch_list = lambda: ([], [])
    import attach
    attach.read = lambda atts, max_pages=12: ("企业会计准则解释第22号\n一、关于售后租回交易的列报\n二、关于数据资源的收入确认", "1.解释.pdf")
    calls = []

    def fake_summarize(item, text):
        calls.append(item["id"])
        return {"title_zh": "测试", "summary": "摘要", "changes": [], "effective_date": None,
                "comment_deadline": "2026-10-11" if "征求" in item["title"] else None,
                "affects": None, "standards": [{"cas": "CAS 21 租赁", "ifrs": "IFRS 16 租赁"}],
                "type": None, "importance": "高", "importance_reason": "", "model": "fake"}
    summarize.summarize = fake_summarize
    os.environ["ANTHROPIC_API_KEY"] = "test"

    with tempfile.TemporaryDirectory() as d:
        fetch.DATA = Path(d) / "data.json"
        fetch.META = Path(d) / "meta.json"
        fetch.main()
        db = json.loads(fetch.DATA.read_text("utf-8"))
        n1 = len(db["items"])
        check(n1 == 5, f"首次运行 5 条（财政部两个栏目各 2 + IFRS 1，主席专访被过滤），实际 {n1}")
        check(len(calls) == 5, "每条都生成了摘要")
        check(len(db["skipped"]) >= 2, f"不相关的记进 skipped：{len(db['skipped'])}")
        check(all(it["ai"] for it in db["items"]), "摘要已写入")
        check("CAS 21" in db["items"][0]["standards"], "AI 给出的准则编号并入 standards")
        check(db["sources"]["mof"]["ok"] and db["sources"]["ifrs"]["ok"], "来源状态正常")
        ifrs_it = [x for x in db["items"] if x["source"] == "ifrs"][0]
        check(ifrs_it["auto"]["title_zh"].startswith("【译】"), "IFRS 有中文标题")
        mof_it = [x for x in db["items"] if "征求" in x["title"]][0]
        check(mof_it["auto"].get("changes") == ["一、关于售后租回交易的列报", "二、关于数据资源的收入确认"], f"附件标题作要点：{mof_it['auto'].get('changes')}")
        check(mof_it["auto"]["comment_deadline"] == "2026-10-11", f"财政部截止日：{mof_it['auto']}")
        meta = json.loads(fetch.META.read_text("utf-8"))
        check(meta["count"] == 5 and len(meta["version"]) == 12, "meta.json")
        calls.clear()
        fetch.main()
        db2 = json.loads(fetch.DATA.read_text("utf-8"))
        check(len(db2["items"]) == 5 and not calls, "第二次运行不重复添加、不重复调用 AI")
        meta2 = json.loads(fetch.META.read_text("utf-8"))
        check(meta2["version"] == meta["version"], "数据没变时 version 不变（App 就不用重新下载）")
        # 输出一份样例数据给 App 测试用
        (ROOT / "tests" / "sample-data.json").write_text(fetch.DATA.read_text("utf-8"), "utf-8")


if __name__ == "__main__":
    test_parsers()
    test_csrc()
    test_csrc_column()
    test_szse()
    test_auto()
    test_main()
    print("\n全部通过" if not check.failed else "\n有失败项")
    sys.exit(1 if check.failed else 0)
