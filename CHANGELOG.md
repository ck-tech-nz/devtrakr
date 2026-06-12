# 更新日志

本项目所有重要变更都将记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 2026-06-11 — Issue 评论 + 看板按列分页 + 优先级/状态颜色配置

Issue 详情页新增 GitHub 风格评论区（@提及通知、作者编辑、管理员删除）;看板改为 GitHub Projects 式按列分页;优先级与状态的颜色/显示名开放为站点设置。

### 新增

- **Issue 评论区**:详情页主栏新增评论列表 + Markdown 编辑器（支持 @提及、贴图、附件卡、任务清单）。作者可编辑自己的评论（显示「已编辑」徽标,内容未变的保存不误标）、作者与管理员可删除（带确认弹窗）;评论后问题 `updated_at` 刷新但不产生历史快照行;dashboard 动态流显示「评论了」;负责人评论计入 KPI 首次响应（有意为之,已加测试钉住）。
- **评论 @提及通知**:评论中 @某人 发站内通知,只通知本次新增的提及,@自己/已停用用户不发;编辑评论只通知新增提及,且同一人 10 分钟窗口内不重复通知（防删了再加回的刷通知）。
- **看板按列分页**:看板每列独立分页（每列 20 条,列内滚动到底自动续取,带「加载更多」兜底按钮）,列头计数显示真实总数;修复了此前看板分页截断导致部分问题不可见的问题（如 #73）。
- **优先级/状态颜色站点设置**:管理后台「站点设置」新增通用颜色选项编辑器,可改各档位的显示名、主色与顺序（档位值锁定——模型与状态流转依赖,不可增删改值）;前端徽章、看板卡片/列圆点、表格行底色、详情页胶囊、优先级滑块均按配置着色,主色仅接受合法 hex(3/4/6/8 位),非法值回退默认色。
- **优先级滑块液态玻璃化**:筛选栏优先级滑块改 iOS 风格玻璃 thumb,轨道为优先级色系渐变,thumb 与当前档 label 对齐,补键盘焦点环;档位与配色随站点设置联动。
- **看板卡片显示更新时间**:负责人行右侧显示相对更新时间（今天 HH:MM / 昨天 / 前天 / MM-DD）。
- **优先级徽章按站点主色着色**:看板卡、待办卡、列表筛选标签的优先级徽章底/字/描边按站点设置主色派生（无主色档位回退语义色）;问题列表接口补 `assignee_avatar` 字段,卡片显示负责人头像。
- **评论写操作限频**:发表/编辑/删除评论 20 次/分钟（每用户）,防脚本刷评论/刷通知。

### 变更

- 看板取数从「全量拉取」改为按列分页（详见上文）,切换视图时按各自形态重新取数;问题列表接口补 `select_related/prefetch_related`,消除列表序列化的逐行 N+1（看板并发取列后该端点请求量倍增）。
- 全局分页器支持客户端 `page_size` 参数（上限 200,超出静默截断;全量拉取需跟随 `next` 翻页）。
- Markdown 渲染:预览图片加描边+阴影与页面底色区分;行内图片改为懒加载（`loading="lazy"`）;MarkdownIt 实例改模块级单例（评论区每条评论一个渲染器实例的开销消除）。
- 关于页构建信息适配 CI 新的两段式 VERSION 格式（`env/<env> <sha>`,镜像层按 SHA 复用）;构建日期前端取构建时刻、后端取 VERSION 文件 mtime。
- 站点设置的 `priorities` / `issue_statuses` 从扁平字符串列表升级为带颜色/显示名的对象列表（数据迁移自动转换,新旧格式后端/前端均兼容）。

### 修复

- USelect 空字符串选项值改用哨兵值,消除 reka-ui SelectItem 报错（多页同步修复）。
- 看板列在翻页期间收缩时,越界页码的 404 不再无限重试（止损置 `hasMore=false`）;切到看板模式时作废在途的表格响应,防止旧响应回填覆盖列表状态。
- 提及显示名转义,防注入 XSS;软删 issue 的评论锁定不可改删;空 PATCH 不标记「已编辑」。

### 技术细节

- 新增 `IssueComment` 模型（迁移 issues 0014/0015,含 (issue, created_at) 复合索引）;评论 API 为 `GET/POST /api/issues/{pk}/comments/` 与 `PATCH/DELETE /api/issues/{pk}/comments/{id}/`,写操作均在事务中。
- 设置迁移 settings 0010/0011 将优先级/状态转换为对象列表,幂等、可回滚（回滚有损:自定义显示名/颜色丢弃,仅保留值列表）。
- CI 构建启用 buildx + GHA 层缓存,前端构建改 `npm ci` + lockfile;VERSION 文件去掉日期改 `env/<env> <sha>`,镜像层可按 SHA 复用。
- 测试:后端新增评论 API/提及服务/边界/KPI 首响语义/头像字段等 40+ 条（共 846 通过）;前端新增评论组件、看板分页 composable/组件、优先级徽章、usePriority/useStatus、timeAgo 等共 52 条（共 95 通过）。
- 本次合入前过了多路 review(checklist/安全/性能/迁移/API 契约/可维护性/设计/红队),遗留改进项见 TODOS.md 与 PR #9 Follow-ups。

### 部署注意

1. 部署后执行迁移:`python manage.py migrate`（issues 0014/0015 建评论表;settings 0010/0011 转换优先级/状态格式,均幂等）。
2. Watchtower 滚动窗口提示:settings 迁移先于全部容器换新镜像生效时,旧代码短暂无法通过优先级校验（创建/改优先级报 400）,全部容器换新后自愈;窗口通常仅数分钟,无需干预。
3. **需手动操作**:`deploy/{test,prod}/docker-compose.yml` 的启动命令改为 `uv run --no-sync`(容器启动不再联网重装依赖)。Watchtower 只拉镜像不会同步 compose 改动,需 `/sync-deploy` 推送 compose 到服务器并 `docker compose up -d --force-recreate`。
4. 无新增页面路由/权限,无需 `sync_page_perms`(评论权限对齐为后续 PR,见 TODOS)。

## 2026-06-10 — 页头公告走马灯 + 问题筛选栏

页头中部新增一条轮播公告（名言 / 提示词 / 避坑 / 价值观 / 公告），配套后台管理页;问题列表的筛选从零散控件收拢成一条可折叠的筛选栏。

### 新增

- **页头走马灯公告**:`HeaderBulletinCarousel` 挂在 AppHeader 中部(仅 lg 及以上显示)。有公告时公告置顶常驻、多条间轮播;无公告时其余四类内容加载后随机洗牌一次、每 8 秒切换、悬停暂停。点击带链接的公告在新标签打开(`rel="noopener noreferrer"`)。
- **走马灯管理页**:设置 → 走马灯管理(`/app/settings/bulletins`),管理员可增删改查公告,设置分类 / 出处 / 链接 / 启用 / 排序 / 生效时间窗。
- **公开公告接口 + 管理接口**:`GET /api/notifications/bulletins/active/`(任意登录用户,精简字段,只返回当前生效项);`/api/notifications/bulletins/manage/`(管理端 CRUD,`FullDjangoModelPermissions` 鉴权)。
- **`useBulletins` 轮询 composable**:模块级单例 + 订阅者引用计数,全站只跑一个 5 分钟定时器,标签页隐藏时不拉取、切回前台立即刷新,全部卸载后停。
- **问题列表可折叠筛选栏**:「只看我的」开关、负责人 / 状态下拉、优先级滑块(`PrioritySlider`),并把当前生效的筛选条件汇总成可一键清除的 chips + 计数徽标。

### 变更

- 问题列表 `fetchIssues` 的查询参数拼装抽到纯函数 `~/utils/issueQuery.ts`(`buildIssueQueryParams`):行内徽标(处理人 / 优先级)优先级高于筛选栏下拉,未勾选「显示已完成」且未显式选状态时默认排除「已关闭 / 未计划」。行为不变,便于单测。
- 管理端公告列表查询加 `select_related("created_by")`,避免序列化 `created_by_name` 时的 N+1。

### 修复

- **走马灯组件挂载即崩溃**:`watch(rotating, …, { immediate: true })` 在 `index` 声明之前就写 `index.value`,setup 同步执行命中 TDZ 抛 `ReferenceError`。已把 `index` 等状态移到 watch 之前。由新增组件测试发现。
- **通知发布端点 NameError(历史遗留)**:`ManagePublishView.post` 误调用未定义的 `_generate_recipients`(正确名为 `generate_recipients`),发布任意草稿都会 500。已修正并补回归测试。
- **dashboardLayout 测试失真**:`电话线路状态`(gateway)卡加入注册表后,旧测试仍断言 `server` 末位且漏了 `gateway`,在 main 上一直红。已更新断言。

### 技术细节

- 新增 `Bulletin` 模型 + `BulletinQuerySet.currently_active()`(`is_active` + 包含式 `starts_at`/`ends_at` 时间窗 + `sort_order` 排序);迁移 `0003_bulletin`(建表)。生产环境不预置数据,公告由管理员在「走马灯管理」页创建。
- 前端引入 `@nuxt/test-utils` + `happy-dom` + `@vue/test-utils`:纯 TS 测试仍跑 node,组件 / composable 测试用 `// @vitest-environment nuxt` 注解切到 Nuxt 运行时(`mountSuspended` / `mockNuxtImport`)。
- 测试:后端 bulletin 12 条 + 发布端点回归 4 条(共 803 通过);前端 PrioritySlider / useBulletins / HeaderBulletinCarousel / issueQuery 共 26 条新测试(共 43 通过)。

### 部署注意

1. 部署后执行迁移 `python manage.py migrate notifications`(建 `bulletin` 表;不预置数据)。
2. 运行 `python manage.py sync_page_perms` 同步走马灯管理页路由与 `notifications.{view,add,change,delete}_bulletin` 权限(`page_perms.json` 已加入管理员组)。

## 2026-05-16 — AI Issue Wizard v2

把"AI 提单向导"从 3 段串行的纯文本流水线（≈60 秒）改造成单次多模态调用（≈6–8 秒），并把重复检测合并进同一流程。

### 新增

- **截图直读**：客服 / QA 上传截图后，向导直接把图传给 `qwen-vl-max-latest`，AI 会把截图中的报错、页面、按钮文字写入复现步骤。
- **可能重复 Issue 提示面板**：提交前看到一个可折叠的"发现 N 条可能重复"，列出疑似旧 Issue 的 `ISS-编号 / 标题 / 状态 / 相似原因`。仅提示，不阻止提交，最终决定权在用户。
- **AI 推断环境**：草稿描述里自动追加 `> 🤖 AI 推断环境: 环境 / 角色 / 页面` 引用块，方便工程师快速定位。
- **图片自动内联到描述**：上传的截图以 `![文件名](URL)` 形式写进 Issue 描述，Issue 详情页可直接预览，不必再到右侧附件区翻找。
- **回滚开关 `AI_WIZARD_LEGACY`**：设为 `True` 即可临时切回 v1 三段流水线，无需重新部署代码。v1 提示词在数据库中保留（已停用），7 天观察期内可一键恢复。

### 变更

- `AiWizardService.stream_draft` 改用 `ThreadPoolExecutor` 并行跑"草稿生成"和"重复检测"两条线，事件按到达顺序通过 SSE 推给前端。
- 向导第二屏（分析中）从 3 行进度合并为 1 行 + "通常 6-8 秒"小提示。
- 向导第三屏（确认草稿）取消手填环境下拉框，改用 AI 推断的环境信息。
- 第一屏占位文字改为提示用户可以贴截图。

### 修复

- **Issue 203 类问题**：通过向导提交的 Issue 关联了截图，但 Issue 详情页正文里看不到预览。现在描述里自动嵌入 `![](url)` markdown，正文内直接渲染。
- **重复 Issue 无提示**：向导流程之前完全没有调用 `check_duplicates`，用户可以连续提交两条一模一样的 Issue。现在并行调用，发现疑似重复会在草稿页弹出折叠面板。

### 技术细节

- 新增 `LLMClient.complete_multimodal(model, system_prompt, user_prompt, images, …)`，构造 OpenAI 兼容的 `content` 数组并把图片 base64 内联。`images=[]` 时退回纯文本，便于 vision 失败后的降级。
- 新增 `apps/tools/storage.read_object(key)` 从 MinIO 读取附件原始字节。
- 新增 `Prompt(slug="wizard_oneshot")`，模型 `qwen-vl-max-latest`，温度 0.3。系统提示词专门针对"客服描述粗糙、混合多问题、截图代替文字"等场景调优。
- 字段校验：标题 ≤200 字、复现步骤 ≤2000 字、预期行为 ≤500 字、`inferred_env` ≤200 字、`labels` 至多 3 个、`follow_up_questions` 至多 3 条且每条 ≤100 字。
- Vision 调用失败时回退纯文本调用，并把 "AI 未能读取截图，已基于文字生成" 作为第一条 `follow_up_questions` 返回给用户。
- LLM 返回非合法 JSON 时重试 1 次（共 2 次尝试），仍失败则抛 `AiWizardError(code="llm_bad_json")`。
- 单元测试覆盖：39 条 wizard 测试 + 全量 464 条后端测试通过。

### 部署注意

1. 部署后执行迁移 `python manage.py migrate ai`（自动 seed `wizard_oneshot`、停用 v1 提示词）。
2. 在 Django Admin 创建 `LLMConfig`：
   - name = `DashScope`
   - base_url = `https://dashscope.aliyuncs.com/compatible-mode/v1`
   - api_key = `DASHSCOPE_API_KEY`
   - supports_json_mode = **取消勾选**（DashScope VL 模型不支持 `response_format=json_object`）
   - is_active = ✓
3. 把 `wizard_oneshot` 提示词的 `llm_config` 绑定到上一步创建的 DashScope 行。
4. 出现问题时，环境变量 `AI_WIZARD_LEGACY=True` + Django Admin 把三条 v1 提示词的 `is_active` 改回 `True` 即可回滚。
