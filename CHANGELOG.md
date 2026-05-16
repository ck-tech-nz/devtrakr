# 更新日志

本项目所有重要变更都将记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
