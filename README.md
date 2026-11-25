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
| `scraper/` | 抓取脚本（Python）。`sources/mof.py` 财政部，`sources/ifrs.py` IFRS，`summarize.py` AI 摘要 |
| `data/` | 自动生成的数据，不要手改 |
| `app/index.html` | App 界面（单文件 HTML），电脑浏览器也能直接打开看 |
| `android/` | 安卓外壳（WebView），由 GitHub 自动打包 |
| `.github/workflows/fetch.yml` | 每日抓取 |
| `.github/workflows/build-apk.yml` | 改了 `app/` 或 `android/` 后自动打包 APK，发布到 Releases |
| `tests/test_offline.py` | 离线测试：`python tests/test_offline.py` |

## 第一次设置

1. **建仓库**：在 GitHub 新建**公开**仓库 `standards-tracker`，把本文件夹全部推上去（包括 `.github` 文件夹）。
   仓库名如果不一样，要改 `app/index.html` 里的 `DEFAULT_DATA_BASE`，或在 App“设置 → 数据地址”里改。
2. **填密钥**：仓库 Settings → Secrets and variables → Actions → New repository secret，添加两个：
   - `ANDROID_KEYSTORE_B64`：签名钥匙，见单独发给你的 `签名钥匙-勿上传.txt`
   - `ANDROID_KEYSTORE_PASSWORD`：签名密码，同上
3. **第一次抓取**：Actions → “抓取准则动态” → Run workflow。跑完看日志，最后几行会显示每个来源新增多少条、有没有报错。
4. **装 App**：Actions → “打包安卓 APK” → Run workflow。打包完成后到仓库首页右侧的 Releases 下载 APK 安装。
5. **坚果云**（可选）：App → 设置 → 填账号和应用密码 → 保存并同步。

## 费用

- GitHub：公开仓库的 Actions 免费。
- AI 摘要：默认用 **GitHub Models 免费额度**（模型 `openai/gpt-4.1-mini`），不用填任何密钥。
  免费额度每天有次数限制，用完了当天剩下的摘要会在下次运行时自动补上；每次最多 40 条。
  想换模型：Settings → Secrets and variables → Actions → Variables 里加 `GITHUB_MODEL`。
  以后想用质量更好的 Claude：在 Secrets 里加 `ANTHROPIC_API_KEY`，会自动改用 Claude（付费）。

## 可能遇到的问题

- **财政部抓取失败**：中国政府网站有时会拦截境外服务器，GitHub 的服务器在境外。App 顶部会出现红色提示，“设置 → 数据来源”里能看到错误信息。
  如果一直失败，可以改成在自己电脑上用 Windows 任务计划每天运行 `python scraper/fetch.py`，再 `git push`。
- **网站改版**：解析不出内容时，来源状态会变成“失败”，需要修改 `scraper/sources/` 里对应的文件。
- **IFRS 新闻列表**：ifrs.org 的新闻列表是网页脚本动态加载的，所以改为读取 `sitemap.xml` 来发现新文章。

## 以后加来源

数据结构已经预留了四类体系：`中国准则 / IFRS / 可持续 / 审计监管`。新增一个来源（如中注协、证监会、IAASB）的方法：
在 `scraper/sources/` 新建一个文件，仿照 `mof.py` 写好列表解析，再在 `fetch.py` 里加一段调用。
