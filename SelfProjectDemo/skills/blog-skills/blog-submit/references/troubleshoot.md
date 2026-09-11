# 线上同步故障排查手册

症状驱动的排查顺序：先确认"到底是哪一环断了"，再对症处理。本文只在出问题时读取。

## 发布链路（排查前心里先有这张图）

    源文件 content/posts/*.md
      → ./hugo 生产构建 → docs/
      → git add / commit / push → GitHub main 分支
      → GitHub Pages 部署（约 1~2 分钟）
      → https://hyc031.github.io/

线上只是链路的末端，任何一环断掉，用户看到的都是"线上不对"。排查就是从症状出发，逐环往回找断点。

## 按症状查

### 症状 A：线上没有这篇文章（404，或文章列表里没有）

按顺序检查，每一步都给出结论再进下一步：

1. `git -C E:/Blog/hyc status`——文章是否处于已修改未提交、或整个未跟踪状态？是 → 本地改动从没走完发布流程，转主流程
2. 源文件 front matter 的 `draft` 是否为 `true`？是 → 命中历史坑 ①，改 false 后重新构建提交
3. `ls E:/Blog/hyc/docs/posts/`——docs 里有没有这篇文章的目录？没有 → 生产构建把它跳过了（draft、date 异常或构建报错），重新 `./hugo` 并看输出
4. `git log --oneline -5` + `git show --stat HEAD`——最近的提交里有没有 docs/ 的改动？只有源文件没有 docs → 命中历史坑 ②，重新构建后把 docs/ 一起提交
5. `git status` 显示与 origin/main 同步吗？不同步 → 还没 push，推完再等部署
6. 以上全部正常 → 大概率是 Pages 部署延迟，等 2 分钟后 `curl -s https://hyc031.github.io/sitemap.xml` 再看

### 症状 B：文章在线上，但内容是旧版本

1. `git -C E:/Blog/hyc status`——本地有未提交的修改？是 → 改动停在本地，转主流程提交
2. 对比源文件与 `docs/posts/<文章>/index.html`：docs 落后于源文件 → 命中历史坑 ②，重新构建提交
3. 仓库内容也同步 → 部署延迟，等待后重查

### 症状 C：文章在线上，图片 404

1. 从线上页面拿到 404 图片的确切 URL
2. 核对 `content/posts/images/` 下文件是否存在、文中引用路径是否与之一致（大小写也要一致）
3. `git -C E:/Blog/hyc ls-files content/posts/images/`——图片没被 git 跟踪？是 → 命中历史坑 ③，add 后重走提交
4. 图片在仓库里但 `docs/posts/images/` 里没有 → 重新构建

### 症状 D：整站 404 或样式全挂

1. `docs/.nojekyll` 还在吗？丢了 → 命中历史坑 ④，补一个空文件重新提交
2. hugo.yaml 的 `baseURL` 是否还是 `https://hyc031.github.io/`？被改过 → 恢复后重新构建
3. `grep -r "livereload" docs/` 有输出 → 开发服务器的产物被当成了生产产物，重新 `./hugo` 后提交

## 历史踩坑记录（每次修完线上问题，把新案例追加到这里）

| 时间 | 症状 | 根因 | 沉淀出的检查项 |
| --- | --- | --- | --- |
| 2026-08 | ch5 文章线上不出现 | date 是未来时间，生产构建默认跳过 | hugo.yaml 已设 `buildFuture: true`，勿移除 |
| 2026-08 | 需要补 .nojekyll（提交 eeb43b2） | docs/.nojekyll 缺失，GitHub Pages 会按 Jekyll 处理导致下划线资源 404 | 提交前核对 .nojekyll 存在（主流程第 2 步） |
| 2026-08 | 线上产物残留 localhost/livereload（提交 e1526c7 清除） | 开发服务器的产物被提交上线 | 只用 `./hugo` 生产构建，构建后 grep 检查（主流程第 2 步） |
| 2026-09 | SKill内容.md 线上一直看不到 | `draft: true` 未关 + 后续修改未提交 + 配图目录未跟踪 | draft 是第一查项；改完必须重走全流程（主流程第 1、4 步） |
