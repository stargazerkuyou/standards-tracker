# 准则追踪

追踪中国企业会计准则和 IFRS（含 ISSB 可持续披露）的最新动态。每天自动抓取，AI 生成中文摘要，手机 App 查看。

```
GitHub Actions（每天北京时间 7:17）
  抓财政部会计司 + IFRS 基金会 → AI 中文摘要 → 更新 data/data.json
手机 App
  打开时检查 data/meta.json，有变化才下载 data.json → 新条目标红点
  已读 / 收藏 / 笔记 → 坚果云同步
```

## 目录

| 路径 | 作用 |
|---|---|
| `scraper/` | 抓取脚本（Python）。`sources/mof.py` 财政部（含企业会计准则实施问答、应用案例），`sources/szse.py` 深交所《会计监管动态》，`sources/ifrs.py` IFRS，`sources/csrc.py` 证监会会计监管，`auto.py` 机器翻译和规则提取，`summarize.py` AI 摘要（可选） |
| `data/` | 自动生成的数据，不要手改 |
| `app/index.html` | App 界面（单文件 HTML），电脑浏览器也能直接打开看 |
| `android/` | 安卓外壳（WebView），由 GitHub 自动打包。签名钥匙也在这里（个人自用，只从自己仓库的 Releases 下载安装） |
| `.github/workflows/fetch.yml` | 每日抓取 |
| `.github/workflows/build-apk.yml` | 改了 `app/` 或 `android/` 后自动打包 APK，发布到 Releases |
| `tests/test_offline.py` | 离线测试：`python tests/test_offline.py` |

## 第一次设置

1. **建仓库**：在 GitHub 新建**公开**仓库 `standards-tracker`，把本文件夹全部推上去（包括 `.github` 文件夹）。
   仓库名如果不一样，要改 `app/index.html` 里的 `DEFAULT_DATA_BASE`，或在 App“设置 → 数据地址”里改。
2. **填 AI 密钥**（免费）：用 Google 账号打开 aistudio.google.com → Get API key → Create API key，复制。
   到仓库 Settings → Secrets and variables → Actions → New repository secret，Name 填 `GEMINI_API_KEY`，Secret 粘贴密钥。
   签名钥匙已经放在 `android/app/release.keystore`，不用另外设置。
3. **第一次抓取**：Actions → “抓取准则动态” → Run workflow。跑完看日志，最后几行会显示每个来源新增多少条、有没有报错。
4. **装 App**：Actions → “打包安卓 APK” → Run workflow。打包完成后到仓库首页右侧的 Releases 下载 APK 安装。
5. **坚果云**（可选）：App → 设置 → 填账号和应用密码 → 保存并同步。

## 费用

- GitHub：公开仓库的 Actions 免费。
- AI 摘要：用谷歌 Gemini 的**免费额度**（不绑信用卡就不会扣费），每天有次数限制，用完了剩下的摘要下次运行自动补；每次最多 40 条。
  模型会自动挑当前可用的 Flash 系列；想指定就在 Variables 里加 `GEMINI_MODEL`。
  （GitHub Models 已于 2026 年 7 月停用，不能用。）

## 只收哪些内容

`scraper/relevance.py` 决定收不收：只要准则、解释、应用指南、实施问答、案例、会计监管规则/报告、
IASB/ISSB 每月会议决定、可持续披露、XBRL 分类标准；人事任免、机构治理、注册会计师行业、播客演讲论坛、
国际合作与趋同、非企业会计（行政事业单位、社保基金、管理会计、考试）都不收。
不相关的条目直接丢弃，网址记在 `data.json` 的 `skipped` 里，以后不再抓。想调整就改那个文件里的词表。

## 可能遇到的问题

- **财政部抓取失败**：中国政府网站有时会拦截境外服务器，GitHub 的服务器在境外。App 顶部会出现红色提示，“设置 → 数据来源”里能看到错误信息。
  如果一直失败，可以改成在自己电脑上用 Windows 任务计划每天运行 `python scraper/fetch.py`，再 `git push`。
- **网站改版**：解析不出内容时，来源状态会变成“失败”，需要修改 `scraper/sources/` 里对应的文件。
- **IFRS 新闻列表**：ifrs.org 的新闻列表是网页脚本动态加载的，所以改为读取 `sitemap.xml` 来发现新文章。

## 以后加来源

数据结构已经预留了四类体系：`中国准则 / IFRS / 可持续 / 监管`（证监会会计监管归“监管”）。新增一个来源的方法：
在 `scraper/sources/` 新建一个文件，仿照 `mof.py` 写好列表解析，再在 `fetch.py` 里加一段调用。
