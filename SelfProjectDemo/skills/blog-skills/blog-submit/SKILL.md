---
name: blog-submit
description: 管理 hyc Hugo 博客（E:\Blog\hyc，线上 https://hyc031.github.io/）的新建文章、内容审查、构建、git 提交发布与线上同步故障排查。凡用户提到发博客、提交博客、发布文章、更新文章、新建文章、文章线上看不到、图片 404、本地和线上内容不一致等意图，一律使用本 skill——哪怕用户只说了两个字"提交"。
---

# blog-submit：hyc 博客建稿与发布

## 环境事实（先记住，全程要用）

- 站点根目录：`E:\Blog\hyc`（git 仓库，main 分支）。hugo.exe 就在这个目录里，用 `./hugo` 调用
- 文章源文件：`E:\Blog\hyc\content\posts\*.md`，配图放 `content/posts/images/`
- 构建输出：`E:\Blog\hyc\docs\`（hugo.yaml 里 `publishDir: docs`）
- 发布机制：GitHub Pages 从仓库 main 分支的 `docs/` 目录发布，远程为 `github.com/hyc031/hyc031.github.io`
- 线上地址：https://hyc031.github.io/
- hugo.yaml 中 `buildFuture: true` 已开启（未来日期的文章会被构建），`baseURL` 指向线上域名——这两项都不要动
- `docs/.nojekyll` 必须始终存在，丢了会整站异常
- git 提示 "CRLF will be replaced by LF" 无害，忽略即可

## 场景路由

| 用户意图 | 走哪条流程 |
| --- | --- |
| 新建一篇文章（还没动笔或刚建文件） | 先走「新建文章」，写完进入主流程 |
| 发布/提交已写好的文章（首次发布） | 主流程 |
| 修改已发布的文章 | 主流程（同一套检查，一项都不能省） |
| 线上和本地不一样、文章没更新、图片 404 | 读 `references/troubleshoot.md`，按手册排查 |

## 主流程：发布一篇文章

按 5 步顺序执行，不要跳步。第 3 步是硬性暂停点。

### 第 1 步 · 内容审查

**技术检查**（逐项核对，任何一项不过就先处理再继续）：

1. front matter 完整：title、date、draft、categories、tags 都在
2. `draft: false`——最重要的一项。`draft: true` 时生产构建会直接跳过这篇文章，线上永远看不到，而本地 `hugo server` 看起来一切正常，极易漏检（本博客真实踩过）
3. date 是带时区的 ISO 格式，如 `2026-09-01T17:00:00+08:00`
4. 图片核对：文中每个 `./images/...` 引用，对应文件必须真实存在于 `content/posts/images/` 下；新增的图片目录往往还没被 git 跟踪，第 4 步要留意
5. 文件名会成为 URL 的一部分，发布后不要随意改名（改了等于换了 URL，旧链接全失效）

**质量通读**（把全文读一遍，向用户报告，不要擅自改动）：

- 错别字、明显语病
- 未写完的痕迹：结尾突兀、只剩占位句、TODO
- 重复或前后矛盾的段落
- 示例代码块的内容是否和正文说法一致

报告分两档：先列"必须修"（技术检查不过项），再列"建议改"（通读发现），等用户表态。

**本地预览（可选）**：仅当用户说"先预览"时，运行 `./hugo server -b "http://localhost:1313/"` 并等用户在浏览器确认。默认跳过，用第 2 步的构建产物检查代替。

### 第 2 步 · 构建

在站点根目录执行：

```bash
./hugo
```

以下全部满足才算通过：

- 退出码 0，输出无 ERROR
- `docs/posts/` 下出现（或更新）了该文章的目录
- 新增图片已被拷贝到 `docs/posts/images/`
- `docs/` 里 grep 不到 `localhost`、`livereload` 残留
- `docs/.nojekyll` 仍然存在

任何一条不满足，先查明原因，不要带病提交。

### 第 3 步 · 暂停等确认（硬性，不可跳过）

构建通过后停下来，向用户汇报：

- 审查结论（"必须修"项是否已解决）
- 构建结果与产物核对情况
- git 变更摘要（新增/修改/未跟踪了哪些文件）
- 拟用的 commit message

用户明确同意（"推吧"、"ok"、"发布"）才进入第 4 步。用户提出修改就回到第 1 步。

### 第 4 步 · 提交推送

```bash
git add .
git commit -m "feat: <按本次实际内容写描述>"
git push origin main
```

- commit message 沿用仓库惯例：`feat:` / `fix:` 前缀 + 中文描述，写"这次加了什么"，不要千篇一律
- push 失败先看报错：网络问题就重试；提示落后于远程就先 `git pull --rebase` 再推，并告诉用户发生了什么

### 第 5 步 · 上线验证

GitHub Pages 部署通常需要 1~2 分钟：

1. 等待后请求线上 sitemap：`curl -s https://hyc031.github.io/sitemap.xml`，确认新文章 URL 在列
2. 再请求文章页面本身，确认返回 200 且页面里有文章标题
3. 不通过就等一分钟重试；连续失败转 `references/troubleshoot.md`

最后向用户报告：发布成功 + 线上链接。

## 新建文章

在站点根目录执行：

```bash
./hugo new content posts/<文件名>.md
```

- archetype 会自动填 date 和 `draft: true`——草稿期这样是对的，发布时第 1 步会把它揪出来
- 文件名建议小写英文加短横线（如 `hugo-beginners.md`），它会成为 URL 的一部分；现有文章也有用中文名的，尊重用户选择
- 生成后把 title、categories、tags 填全，正文写完后再走主流程

## 修改已发布的文章

与首次发布走完全相同的主流程。两点特别提醒：

- 改完源文件不重新构建 docs/ 就提交，线上永远是旧版（本博客真实踩过）——这正是第 2 步存在的原因
- 改动再小，技术检查可以做得快，但一项都不能省
