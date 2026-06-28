<template>
  <div v-if="loading" class="flex items-center justify-center py-20">
    <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
  </div>

  <div v-else-if="issue" class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <NuxtLink to="/app/issues" class="text-gray-400 dark:text-gray-500 hover:text-gray-600">
          <UIcon name="i-heroicons-arrow-left" class="w-5 h-5" />
        </NuxtLink>
        <h1 class="text-2xl font-semibold">
          <span class="text-gray-900 dark:text-gray-100">{{ issue.title }}</span>
          <span class="text-gray-400 dark:text-gray-500 font-normal ml-2">#{{ issue.id }}</span>
        </h1>
      </div>
      <div class="flex items-center space-x-2">
        <UButton
          v-if="can('issues.delete_issue')"
          icon="i-heroicons-trash"
          color="error"
          variant="outline"
          size="sm"
          title="删除"
          aria-label="删除"
          @click="showDeleteConfirm = true"
        />
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Main content -->
      <div class="lg:col-span-2 space-y-4">
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
          <div class="space-y-4">
            <!-- 标题 -->
            <div class="form-row">
              <div class="flex items-center justify-between h-5">
                <label>标题</label>
                <FieldSaveStatus :saving="savingField === 'title'" :saved="savedField === 'title'" />
              </div>
              <UInput v-model="form.title" @blur="handleBlurSave('title')" />
            </div>

            <!-- 描述 -->
            <div class="form-row">
              <div class="flex items-center justify-between h-5">
                <label>描述</label>
                <FieldSaveStatus :saving="savingField === 'description'" :saved="savedField === 'description'" />
              </div>
              <MarkdownEditor ref="descriptionEditor" v-model="form.description" placeholder="添加描述..." :default-mode="isNewIssue ? 'edit' : 'preview'" min-height="520px" @upload-complete="handleUploadComplete" @blur="handleBlurSave('description')" />
            </div>

          </div>
        </div>

        <!-- 评论 -->
        <IssueComments v-if="!isNewIssue && issue?.id" :issue-id="issue.id" />
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <button class="flex items-center gap-1.5 min-w-0 flex-1 text-left" @click="togglePanel('ai')">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">AI 分析</h3>
              <UIcon :name="panelOpen.ai ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400 shrink-0" />
            </button>
            <div class="flex items-center gap-2 shrink-0">
              <ServiceStatusDot :online="isOnline('ai')" />
              <UButton
                v-if="issue.repo"
                size="xs"
                variant="soft"
                icon="i-heroicons-cpu-chip"
                :loading="aiAnalyzing"
                :disabled="aiAnalyzing || issueRepo?.clone_status !== 'cloned'"
                @click="triggerAIAnalysis"
              >{{ aiAnalyzing ? '分析中...' : '分析' }}</UButton>
            </div>
          </div>

          <div v-if="panelOpen.ai" class="space-y-3">
          <!-- 运行状态 -->
          <div v-if="aiAnalyzing" class="space-y-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-cpu-chip" class="w-4 h-4 text-blue-500 animate-spin" />
              <span class="text-sm text-blue-500 dark:text-blue-400">正在分析代码...</span>
            </div>
            <div class="text-xs text-gray-400">opencode 正在分析仓库代码，通常需要 1-3 分钟</div>
            <div class="w-full bg-gray-100 dark:bg-gray-800 rounded-full h-1.5 overflow-hidden">
              <div class="bg-blue-500 h-1.5 rounded-full ai-progress-bar"></div>
            </div>
          </div>

          <!-- 前置条件提示 -->
          <div v-else-if="!issue.repo" class="text-sm text-gray-400 dark:text-gray-500">请先关联仓库</div>
          <div v-else-if="issueRepo?.clone_status !== 'cloned'" class="text-sm text-gray-400 dark:text-gray-500">请先同步仓库代码</div>

          <!-- 最新分析结果 -->
          <div v-if="latestAnalysis" class="space-y-2">
            <div class="rounded-lg border text-sm"
              :class="latestAnalysis.status === 'failed' ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20' : 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20'">
              <div class="px-3 py-2 max-h-[480px] overflow-y-auto">
                <div class="flex items-center justify-between text-xs mb-1">
                  <div class="flex items-center gap-1" :class="latestAnalysis.status === 'failed' ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'">
                    <UIcon name="i-heroicons-cpu-chip" class="w-3 h-3" />
                    <span>{{ latestAnalysis.created_at?.slice(0, 16).replace('T', ' ') }}</span>
                  </div>
                  <UBadge :color="latestAnalysis.triggered_by === 'manual' ? 'primary' : 'neutral'" variant="subtle" size="xs">
                    {{ latestAnalysis.triggered_by === 'manual' ? '手动' : '自动' }}
                  </UBadge>
                </div>
                <div v-if="latestAnalysis.status === 'failed'" class="text-xs text-red-600 dark:text-red-400">{{ latestAnalysis.error_message }}</div>
                <div v-else-if="latestAnalysis.status === 'running'" class="text-xs text-blue-500">分析中...</div>
                <template v-else-if="latestAnalysis.results">
                  <div v-for="(content, field) in latestAnalysis.results" :key="field" class="mt-1">
                    <div class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ fieldLabel(field as string) }}</div>
                    <div class="markdown-body text-sm mt-0.5 text-gray-700 dark:text-gray-300" v-html="renderMarkdown(content as string)"></div>
                  </div>
                </template>
              </div>
            </div>
          </div>
          <p v-else-if="!aiAnalyzing && issue.repo && issueRepo?.clone_status === 'cloned'" class="text-sm text-gray-400 dark:text-gray-500">暂无分析记录</p>
          </div>
        </div>

        <!-- 属性: 优先级 / 状态 / 负责人 / 求助 / 标签 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-4">
          <button class="flex items-center justify-between w-full" @click="togglePanel('attrs')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">属性</h3>
            <UIcon :name="panelOpen.attrs ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="panelOpen.attrs" class="space-y-4">
          <!-- 优先级 & 状态 -->
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-gray-400 dark:text-gray-500">优先级</label>
            <div class="flex items-center gap-2 flex-wrap">
              <button
                v-for="p in priorityItems"
                :key="p.value"
                class="px-3 py-1 min-w-12 text-center rounded-full text-xs font-medium transition-colors"
                :class="issue.priority === p.value ? 'option-chip-active' : 'option-chip'"
                :style="{ '--chip': p.cssColor, '--chip-text': p.textOn }"
                @click="updateField('priority', p.value)"
              >{{ p.label }}</button>
            </div>
          </div>
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-gray-400 dark:text-gray-500">状态</label>
            <div class="flex items-center gap-2 flex-wrap">
              <button
                v-for="s in statusItems"
                :key="s.value"
                class="px-3 py-1 min-w-12 text-center rounded-full text-xs font-medium transition-colors"
                :class="issue.status === s.value ? 'option-chip-active' : 'option-chip'"
                :style="{ '--chip': s.cssColor, '--chip-text': s.textOn }"
                @click="handleStatusClick(s.value)"
              >{{ s.label }}</button>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="form-row">
              <label class="text-gray-400 dark:text-gray-500">负责人</label>
              <USelect v-model="form.assignee" :items="assigneeItems" placeholder="选择负责人" value-key="value" @update:model-value="(v: string) => autoSave('assignee', v)" />
            </div>
            <div class="form-row">
              <div class="flex items-center gap-2">
                <label class="text-gray-400 dark:text-gray-500">求助</label>
                <FieldSaveStatus :saving="savingField === 'helpers'" :saved="savedField === 'helpers'" />
              </div>
              <USelectMenu v-model="form.helpers" :items="helperItems" multiple placeholder="选择协助人" value-key="value" label-key="label" @update:model-value="onHelpersChange" />
            </div>
          </div>
          <div class="space-y-1.5">
            <UPopover v-model:open="showLabelPicker">
              <button class="flex items-center justify-between w-full group cursor-pointer">
                <label class="text-xs font-medium text-gray-400 dark:text-gray-500 cursor-pointer">标签</label>
                <UIcon name="i-heroicons-cog-6-tooth" class="w-4 h-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300" />
              </button>
              <template #content>
                <div class="w-72 p-0">
                  <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
                    <p class="text-xs font-semibold text-gray-900 dark:text-gray-100">应用标签</p>
                  </div>
                  <div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
                    <UInput v-model="labelSearchQuery" placeholder="筛选标签" size="xs" icon="i-heroicons-magnifying-glass" />
                  </div>
                  <div class="max-h-64 overflow-y-auto">
                    <button
                      v-for="name in filteredLabelNames"
                      :key="name"
                      class="flex items-start gap-2 w-full px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                      @click="toggleLabel(name)"
                    >
                      <UIcon
                        :name="form.labels.includes(name) ? 'i-heroicons-check' : ''"
                        class="w-4 h-4 mt-0.5 shrink-0"
                        :class="form.labels.includes(name) ? 'text-gray-900 dark:text-gray-100' : 'text-transparent'"
                      />
                      <span
                        class="w-3 h-3 rounded-full mt-1 shrink-0"
                        :style="{ backgroundColor: labelItems[name]?.background || '#ccc' }"
                      />
                      <div class="min-w-0">
                        <div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ name }}</div>
                        <div v-if="labelItems[name]?.description" class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ labelItems[name].description }}</div>
                      </div>
                    </button>
                    <div v-if="!filteredLabelNames.length" class="px-3 py-4 text-center text-xs text-gray-400">无匹配标签</div>
                  </div>
                  <button
                    class="w-full px-3 py-2 text-xs text-center text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                    @click="showLabelPicker = false; showLabelManager = true"
                  >编辑标签</button>
                </div>
              </template>
            </UPopover>
            <!-- Applied labels as colored pills -->
            <div class="flex items-center gap-1.5 flex-wrap">
              <span
                v-for="lbl in form.labels"
                :key="lbl"
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :style="{
                  backgroundColor: labelItems[lbl]?.background || '#e5e7eb',
                  color: labelItems[lbl]?.foreground || '#374151',
                }"
              >{{ lbl }}</span>
              <span v-if="!form.labels.length" class="text-xs text-gray-400 dark:text-gray-500">无标签</span>
            </div>
          </div>
          </div>
        </div>
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('info')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">信息</h3>
            <UIcon :name="panelOpen.info ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="panelOpen.info">
          <!-- 宽度足够时两列并排;不够时"预计完成"日历自动换行独占一行 -->
          <div class="flex flex-wrap gap-4">
            <!-- 左列: 元信息 + 工时 -->
            <div class="flex-1 min-w-[8rem] space-y-3">
              <div class="text-sm">
                <span class="text-gray-400 dark:text-gray-500">提出人</span>
                <p class="text-gray-900 dark:text-gray-100 mt-0.5">{{ issue.reporter || issue.created_by_name || '-' }}</p>
              </div>
              <div class="text-sm">
                <span class="text-gray-400 dark:text-gray-500">创建时间</span>
                <p class="text-gray-900 dark:text-gray-100 mt-0.5">{{ issue.created_at?.slice(0, 10) }}</p>
              </div>
              <div v-if="issue.resolved_at" class="text-sm">
                <span class="text-gray-400 dark:text-gray-500">解决时间</span>
                <p class="text-gray-900 dark:text-gray-100 mt-0.5">{{ issue.resolved_at.slice(0, 10) }}</p>
              </div>
              <div v-if="issue.resolution_hours" class="text-sm">
                <span class="text-gray-400 dark:text-gray-500">解决耗时</span>
                <p class="text-gray-900 dark:text-gray-100 mt-0.5">{{ issue.resolution_hours }}h</p>
              </div>
              <div class="form-row">
                <div class="flex items-center justify-between">
                  <label class="text-gray-400 dark:text-gray-500">预计工时</label>
                  <UButton
                    v-if="canEditEstimatedHours && isFieldDirty('estimated_hours')"
                    size="xs"
                    variant="soft"
                    :loading="savingField === 'estimated_hours'"
                    @click="saveField('estimated_hours')"
                  >
                    保存
                  </UButton>
                </div>
                <UInput
                  v-if="canEditEstimatedHours"
                  v-model="form.estimated_hours"
                  type="number"
                  placeholder="小时"
                  step="0.5"
                  min="0"
                />
                <p v-else class="text-sm text-gray-900 dark:text-gray-100 mt-0.5">
                  {{ form.estimated_hours ? `${form.estimated_hours} 小时` : '-' }}
                </p>
              </div>
              <div class="form-row">
                <div class="flex items-center justify-between">
                  <label class="text-gray-400 dark:text-gray-500">实际工时</label>
                  <UButton v-if="isFieldDirty('actual_hours')" size="xs" variant="soft" :loading="savingField === 'actual_hours'" @click="saveField('actual_hours')">保存</UButton>
                </div>
                <UInput v-model="form.actual_hours" type="number" placeholder="小时" />
              </div>
            </div>
            <!-- 右列: 预计完成日历(放不下时换行独占一行) -->
            <div class="form-row shrink-0">
              <label class="text-gray-400 dark:text-gray-500">预计完成</label>
              <UCalendar
                :model-value="calendarValue"
                size="xs"
                class="w-fit"
                :ui="{ cellTrigger: 'data-[selected]:bg-red-500 dark:data-[selected]:bg-red-600' }"
                @update:model-value="onCalendarUpdate"
              />
            </div>
          </div>
          </div>
        </div>

        <!-- 分析记录 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('analysis')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">分析记录</h3>
            <UIcon :name="panelOpen.analysis ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="panelOpen.analysis" class="space-y-4">
            <div class="form-row">
              <div class="flex items-center justify-between h-5">
                <label>备注</label>
                <FieldSaveStatus :saving="savingField === 'remark'" :saved="savedField === 'remark'" />
              </div>
              <UTextarea v-model="form.remark" :rows="2" placeholder="备注信息" @blur="handleBlurSave('remark')" />
            </div>
            <div class="form-row">
              <div class="flex items-center justify-between h-5">
                <label>原因分析</label>
                <FieldSaveStatus :saving="savingField === 'cause'" :saved="savedField === 'cause'" />
              </div>
              <UTextarea v-model="form.cause" :rows="3" :placeholder="latestAiCause ? `[AI] ${latestAiCause}` : '问题原因'" @blur="handleBlurSave('cause')" />
            </div>
            <div class="form-row">
              <div class="flex items-center justify-between h-5">
                <label>解决方案</label>
                <FieldSaveStatus :saving="savingField === 'solution'" :saved="savedField === 'solution'" />
              </div>
              <UTextarea v-model="form.solution" :rows="3" :placeholder="latestAiSolution ? `[AI] ${latestAiSolution}` : '解决办法'" @blur="handleBlurSave('solution')" />
            </div>
          </div>
        </div>

        <!-- 关联附件 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <button class="flex items-center gap-1.5 min-w-0 flex-1 text-left" @click="togglePanel('attachments')">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联附件</h3>
              <UIcon :name="panelOpen.attachments ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400 shrink-0" />
            </button>
            <UButton size="xs" variant="soft" color="primary" icon="i-heroicons-plus" title="添加附件" aria-label="添加附件" @click="attachmentInputRef?.click()" />
          </div>
          <input ref="attachmentInputRef" type="file" multiple class="hidden" @change="handleAttachmentSelect" />

          <div v-if="panelOpen.attachments" class="space-y-3">
          <!-- 图片附件：缩略图网格 -->
          <div v-if="imageAttachments.length" class="grid grid-cols-2 gap-2">
            <div
              v-for="att in imageAttachments"
              :key="att.id"
              class="relative group rounded-lg overflow-hidden border border-gray-100 dark:border-gray-800"
            >
              <img :src="att.file_url" :alt="att.file_name" class="w-full h-20 object-cover" :title="att.file_name" />
              <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-between p-1 gap-1">
                <button class="text-white text-xs bg-primary-600 hover:bg-primary-700 rounded px-1.5 py-0.5 flex-1" @click.stop="insertAttachmentToDescription(att)">插入</button>
                <button class="text-white text-xs bg-red-600 hover:bg-red-700 rounded px-1.5 py-0.5 flex-1" @click.stop="promptDeleteAttachment(att)">删除</button>
              </div>
            </div>
          </div>

          <!-- 非图片附件：列表 -->
          <div v-if="fileAttachments.length" class="space-y-1">
            <div
              v-for="att in fileAttachments"
              :key="att.id"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800 group"
            >
              <UIcon name="i-heroicons-document" class="w-4 h-4 text-gray-400 shrink-0" />
              <span class="text-xs text-gray-700 dark:text-gray-300 truncate flex-1" :title="att.file_name">{{ att.file_name }}</span>
              <a :href="att.file_url" :download="att.file_name" target="_blank" class="text-xs text-blue-500 hover:text-blue-600 shrink-0">下载</a>
              <button class="text-xs text-red-500 hover:text-red-600 shrink-0 opacity-0 group-hover:opacity-100" @click.stop="deleteAttachment(att.id)">删除</button>
            </div>
          </div>

          <p v-if="!attachments.length" class="text-xs text-gray-400 dark:text-gray-500">暂无附件</p>
          </div>
        </div>

        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('repo')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联仓库</h3>
            <UIcon :name="panelOpen.repo ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>

          <div v-if="panelOpen.repo" class="space-y-2">
            <div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">项目</div>
              <USelect
                v-model="form.project"
                :items="projectOptions"
                placeholder="选择项目"
                value-key="value"
                class="w-full"
                @update:model-value="(v: string) => onProjectChange(v)"
              />
            </div>

            <div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">仓库</div>
              <USelect
                v-model="form.repo"
                :items="issueProjectRepoOptions"
                placeholder="选择仓库"
                value-key="value"
                class="w-full"
                :disabled="!form.project || issueProjectRepoOptions.length === 0"
                @update:model-value="(v: string) => autoSave('repo', v)"
              />
              <p v-if="form.project && issueProjectRepoOptions.length === 0" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                该项目暂无关联仓库
              </p>
            </div>
          </div>

          <div v-if="panelOpen.repo && issueRepo" class="flex items-center gap-2 pt-1">
            <UIcon name="i-heroicons-code-bracket" class="w-4 h-4 text-gray-400" />
            <NuxtLink :to="`/app/repos/${issueRepo.id}`" class="text-sm text-blue-600 dark:text-blue-400 hover:underline truncate">
              {{ issueRepo.full_name }}
            </NuxtLink>
            <UBadge v-if="issueRepo.clone_status === 'cloned'" color="success" variant="subtle" size="xs">已克隆</UBadge>
            <UBadge v-else-if="issueRepo.clone_status === 'cloning'" color="warning" variant="subtle" size="xs">克隆中</UBadge>
            <UBadge v-else color="neutral" variant="subtle" size="xs">未克隆</UBadge>
          </div>
        </div>

        <!-- 关联 Issues — 自动 (AI 创建时去重命中) + 手动; 常显以便空列表时也能点 + 添加 -->
        <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <button class="flex items-center gap-1.5 min-w-0 flex-1 text-left" @click="togglePanel('related')">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联 Issues</h3>
              <UIcon :name="panelOpen.related ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400 shrink-0" />
            </button>
            <UButton
              v-if="!relatedSearchOpen"
              size="xs"
              variant="soft"
              color="primary"
              icon="i-heroicons-plus"
              title="关联其它 issue"
              @click="panelOpen.related = true; openRelatedSearch()"
            />
          </div>

          <div v-if="panelOpen.related" class="space-y-3">
          <div v-if="relatedIssuesResolved.length" class="space-y-1.5">
            <div
              v-for="r in relatedIssuesResolved"
              :key="r.id"
              class="group flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800"
            >
              <span
                v-if="r.kind === 'ai_dup'"
                class="text-[0.625rem] px-1.5 py-px rounded bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-300"
                :title="r.reason || 'AI 创建时识别为相似'"
              >AI</span>
              <span
                v-else
                class="text-[0.625rem] px-1.5 py-px rounded bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
              >人工</span>
              <NuxtLink
                :to="`/app/issues/${r.id}`"
                class="font-mono text-xs text-violet-600 dark:text-violet-400 hover:underline shrink-0"
              >ISS-{{ String(r.id).padStart(3, '0') }}</NuxtLink>
              <span class="text-sm text-gray-700 dark:text-gray-300 truncate flex-1">{{ r.title }}</span>
              <span
                class="text-[0.625rem] px-1.5 py-px rounded shrink-0"
                :class="['已解决', '已发布', '已关闭'].includes(r.status)
                  ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300'
                  : 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300'"
              >{{ r.status }}</span>
              <button
                class="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                title="解除关联"
                @click="removeRelated(r.id)"
              >
                <UIcon name="i-heroicons-x-mark" class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <!-- 手动添加: 搜索框 + 结果列表 -->
          <div v-if="relatedSearchOpen" class="space-y-2 pt-1">
            <UInput
              v-model="relatedSearchQ"
              placeholder="搜索 issue 标题或 ID..."
              icon="i-heroicons-magnifying-glass"
              size="sm"
              @update:model-value="onRelatedSearchInput"
            />
            <div v-if="relatedSearchResults.length" class="max-h-48 overflow-y-auto space-y-1">
              <button
                v-for="cand in relatedSearchResults"
                :key="cand.id"
                type="button"
                class="w-full flex items-center gap-2 px-2 py-1.5 text-left text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                @click="addRelated(cand.id)"
              >
                <span class="font-mono text-xs text-gray-400 shrink-0">ISS-{{ String(cand.id).padStart(3, '0') }}</span>
                <span class="text-gray-700 dark:text-gray-300 truncate">{{ cand.title }}</span>
              </button>
            </div>
            <p v-else-if="relatedSearchQ && !relatedSearching" class="text-xs text-gray-400">无匹配结果</p>
            <div class="flex justify-end">
              <UButton size="xs" variant="ghost" color="neutral" @click="closeRelatedSearch">取消</UButton>
            </div>
          </div>
          </div>
        </div>

        <div v-if="issue.github_issues?.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <button class="flex items-center gap-1.5 min-w-0 flex-1 text-left" @click="togglePanel('github')">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">GitHub 关联</h3>
              <UIcon :name="panelOpen.github ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400 shrink-0" />
            </button>
            <ServiceStatusDot :online="isOnline('github')" />
          </div>

          <div v-if="panelOpen.github" class="space-y-3">
          <!-- 已关联的 GitHub Issues -->
          <div v-if="issue.github_issues?.length" class="space-y-2">
            <div v-for="gh in issue.github_issues" :key="gh.id" class="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
              <div class="min-w-0 flex-1">
                <div class="flex items-center space-x-2">
                  <UBadge :color="gh.state === 'open' ? 'success' : 'neutral'" variant="subtle" size="xs">{{ gh.state }}</UBadge>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ gh.repo_full_name }}#{{ gh.github_id }}</span>
                </div>
                <p class="text-sm text-gray-900 dark:text-gray-100 truncate mt-0.5">{{ gh.title }}</p>
              </div>
              <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="xs" @click="unlinkGitHubIssue(gh.id)" />
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无关联记录</p>

          <!-- 操作按钮 -->
          <div class="flex flex-col gap-2 pt-1">
            <UButton size="xs" variant="outline" color="neutral" icon="i-heroicons-plus" @click="showCreateGH = true" block>
              创建 GitHub Issue
            </UButton>
            <UButton size="xs" variant="outline" color="neutral" icon="i-heroicons-link" @click="openLinkGH" block>
              关联已有 Issue
            </UButton>
          </div>
          </div>
        </div>

        <div v-if="linkedPRs.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('pr')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">关联 PR</h3>
            <UIcon :name="panelOpen.pr ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>

          <div v-if="panelOpen.pr" class="space-y-3">
          <!-- 建议已解决:仅在有合并 PR 且未完成时显示 -->
          <div v-if="suggestResolved" class="flex items-center justify-between gap-2 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 rounded-lg px-3 py-2">
            <span class="text-xs text-emerald-700 dark:text-emerald-300">关联 PR 已合并 · 建议标记为已解决</span>
            <UButton
              v-if="can('issues.change_issue')"
              size="xs"
              color="success"
              variant="soft"
              @click="acceptResolveSuggestion"
            >
              采纳建议
            </UButton>
          </div>

          <div class="space-y-2">
            <a
              v-for="pr in linkedPRs"
              :key="pr.id"
              :href="pr.html_url"
              target="_blank"
              class="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center space-x-2">
                  <UBadge :color="prStateColor(pr.state)" variant="subtle" size="xs">{{ prStateLabel(pr.state) }}</UBadge>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ pr.repo_full_name }}#{{ pr.number }}</span>
                </div>
                <p class="text-sm text-gray-900 dark:text-gray-100 truncate mt-0.5">{{ pr.title }}</p>
              </div>
              <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-4 h-4 text-gray-400 shrink-0" />
            </a>
          </div>
          </div>
        </div>

        <!-- 外部来源 — 仅当真正来自第三方接口且带有元数据时才显示 (ai_wizard 内部生成不算) -->
        <div v-if="hasExternalSource" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('source')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">外部来源</h3>
            <UIcon :name="panelOpen.source ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="panelOpen.source && issue.source_meta" class="space-y-2 text-sm">
            <div v-if="issue.source" class="flex justify-between">
              <span class="text-gray-500 dark:text-gray-400">来源平台</span>
              <span class="text-gray-900 dark:text-gray-100">{{ issue.source }}</span>
            </div>
            <div v-if="issue.source_meta.feedback_id" class="flex justify-between">
              <span class="text-gray-500 dark:text-gray-400">反馈编号</span>
              <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.feedback_id }}</span>
            </div>
            <template v-if="issue.source_meta.reporter">
              <div class="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">报告人信息</span>
              </div>
              <div v-if="issue.source_meta.reporter.user_name" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">姓名</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.reporter.user_name }}</span>
              </div>
              <div v-if="issue.source_meta.reporter.tenant_name" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">租户</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.reporter.tenant_name }}</span>
              </div>
              <div v-if="issue.source_meta.reporter.contact" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">联系方式</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.reporter.contact }}</span>
              </div>
            </template>
            <template v-if="issue.source_meta.context">
              <div class="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">上下文信息</span>
              </div>
              <div v-if="issue.source_meta.context.page_url" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">页面</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.context.page_url }}</span>
              </div>
              <div v-if="issue.source_meta.context.browser" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">浏览器</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.context.browser }}</span>
              </div>
              <div v-if="issue.source_meta.context.os" class="flex justify-between">
                <span class="text-gray-500 dark:text-gray-400">操作系统</span>
                <span class="text-gray-900 dark:text-gray-100">{{ issue.source_meta.context.os }}</span>
              </div>
            </template>
            <template v-if="issue.source_meta.attachments?.length">
              <div class="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">外部附件</span>
              </div>
              <div v-for="(att, idx) in issue.source_meta.attachments" :key="idx">
                <a :href="att.url" target="_blank" class="text-primary-500 hover:underline text-xs">
                  {{ att.type || '附件' }} {{ idx + 1 }}
                </a>
              </div>
            </template>
          </div>
        </div>

        <!-- 分配流转 -->
        <div v-if="issue?.assignments?.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('assignments')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">分配流转</h3>
            <UIcon :name="panelOpen.assignments ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <ol v-if="panelOpen.assignments" class="space-y-1.5 text-sm">
            <li v-for="a in issue.assignments" :key="a.id" class="flex flex-wrap gap-x-2 gap-y-0.5">
              <span class="text-gray-400 dark:text-gray-500 text-xs">{{ formatAssignmentDate(a.created_at) }}</span>
              <span class="font-medium text-gray-700 dark:text-gray-300">{{ assignmentActionLabel(a.action) }}</span>
              <span v-if="a.from_user_name" class="text-gray-500 dark:text-gray-400">from {{ a.from_user_name }}</span>
              <span class="text-gray-500 dark:text-gray-400">→ {{ a.to_user_name }}</span>
              <span v-if="a.reason" class="text-gray-400 dark:text-gray-500 italic">— {{ a.reason }}</span>
            </li>
          </ol>
        </div>

        <!-- 变更历史 (仅管理员) -->
        <div v-if="isManager" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-3">
          <button class="flex items-center justify-between w-full" @click="togglePanel('history')">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">变更历史</h3>
            <UIcon :name="panelOpen.history ? 'i-heroicons-chevron-up' : 'i-heroicons-chevron-down'" class="w-4 h-4 text-gray-400" />
          </button>
          <div v-if="panelOpen.history" class="space-y-3">
            <div v-if="historyLoading" class="text-xs text-gray-400 dark:text-gray-500">加载中...</div>
            <p v-else-if="!history.length" class="text-xs text-gray-400 dark:text-gray-500">暂无历史记录</p>
            <div v-else class="space-y-3 max-h-96 overflow-y-auto -mx-1 px-1">
              <div
                v-for="entry in history"
                :key="entry.id"
                class="border-l-2 pl-3 py-1"
                :class="entry.type === '+' ? 'border-emerald-400' : entry.type === '-' ? 'border-rose-400' : 'border-crystal-300 dark:border-crystal-700'"
              >
                <!-- 执行人 + 时间 -->
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs font-semibold text-gray-700 dark:text-gray-300 min-w-0 truncate">{{ entry.user || '系统' }}</span>
                  <time class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0" :title="formatFullTime(entry.date)">{{ formatRelative(entry.date) }}</time>
                </div>
                <!-- 变更内容(旧值 → 新值) -->
                <ul class="mt-1 space-y-0.5">
                  <li v-for="(line, i) in changeLines(entry)" :key="i" class="text-xs leading-relaxed">
                    <span v-if="line.kind !== 'update'" class="text-gray-500 dark:text-gray-400">
                      {{ line.kind === 'created' ? '创建问题' : '删除问题' }}
                    </span>
                    <template v-else>
                      <span class="font-medium text-gray-600 dark:text-gray-300">{{ line.label }}</span>
                      <span class="text-gray-400 dark:text-gray-500">：</span>
                      <span class="text-gray-400 dark:text-gray-500 break-all">{{ line.before }}</span>
                      <UIcon name="i-heroicons-arrow-small-right" class="inline-block w-3.5 h-3.5 align-text-bottom mx-0.5 text-gray-300 dark:text-gray-600" />
                      <span class="text-gray-700 dark:text-gray-200 break-all">{{ line.after }}</span>
                    </template>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建 GitHub Issue 弹窗 -->
    <UModal v-model:open="showCreateGH" title="创建 GitHub Issue" :ui="{ width: 'sm:max-w-md' }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>创建 GitHub Issue</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showCreateGH = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-500 dark:text-gray-400">将根据当前问题的标题和描述在 GitHub 仓库创建 Issue，并自动关联。</p>
            <div class="form-row">
              <label>目标仓库 <span class="text-red-400">*</span></label>
              <USelect v-model="ghCreateRepo" :items="repoOptions" placeholder="选择仓库" value-key="value" />
            </div>
            <p v-if="ghCreateError" class="text-sm text-red-500">{{ ghCreateError }}</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showCreateGH = false">取消</UButton>
            <UButton :loading="ghCreating" @click="handleCreateGH">创建</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- 删除附件确认弹窗 -->
    <UModal v-model:open="showDeleteAttachmentConfirm">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>删除附件</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showDeleteAttachmentConfirm = false" />
          </div>
          <div class="modal-body space-y-2">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              确认删除附件 <span class="font-medium">{{ pendingDeleteAttachment?.file_name }}</span>？
            </p>
            <p class="text-sm text-gray-500 dark:text-gray-400">是否同时移除描述中的引用？</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showDeleteAttachmentConfirm = false">取消</UButton>
            <UButton color="error" variant="outline" @click="() => { deleteAttachment(pendingDeleteAttachment!.id, false); showDeleteAttachmentConfirm = false }">仅删除文件</UButton>
            <UButton color="error" @click="() => { deleteAttachment(pendingDeleteAttachment!.id, true); showDeleteAttachmentConfirm = false }">删除并移除引用</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- 关联已有 GitHub Issue 弹窗 -->
    <UModal v-model:open="showLinkGH" title="关联 GitHub Issue" :ui="{ width: 'sm:max-w-lg' }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>关联 GitHub Issue</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showLinkGH = false" />
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>筛选仓库</label>
              <USelect :model-value="ghLinkRepoFilter || '_all'" :items="[{ label: '全部', value: '_all' }, ...repoOptions]" value-key="value" @update:model-value="(v: string) => ghLinkRepoFilter = v === '_all' ? '' : v" />
            </div>
            <div class="max-h-60 overflow-y-auto space-y-1 mt-2">
              <div v-for="gh in availableGHIssues" :key="gh.id" class="flex items-center space-x-2 px-2 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer" @click="toggleGHSelection(gh.id)">
                <UCheckbox :model-value="ghSelectedIds.includes(gh.id)" />
                <div class="min-w-0 flex-1">
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ gh.repo_full_name }}#{{ gh.github_id }}</span>
                  <p class="text-sm text-gray-900 dark:text-gray-100 truncate">{{ gh.title }}</p>
                </div>
                <UBadge :color="gh.state === 'open' ? 'success' : 'neutral'" variant="subtle" size="xs">{{ gh.state }}</UBadge>
              </div>
              <p v-if="!availableGHIssues.length" class="text-sm text-gray-400 dark:text-gray-500 text-center py-4">没有可关联的 GitHub Issue</p>
            </div>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showLinkGH = false">取消</UButton>
            <UButton :disabled="!ghSelectedIds.length" :loading="ghLinking" @click="handleLinkGH">关联 ({{ ghSelectedIds.length }})</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Label Management Modal -->
    <UModal v-model:open="showLabelManager" :title="editingLabel || addingLabel ? (addingLabel ? '新增标签' : '编辑标签') : '管理标签'">
      <template #content>
        <!-- Edit / Add view -->
        <div v-if="editingLabel || addingLabel" class="p-5 space-y-5">
          <!-- Preview area -->
          <div class="flex items-center justify-center py-6 rounded-lg bg-gray-50 dark:bg-gray-800/50">
            <span
              class="px-3 py-1 rounded-full text-sm font-medium shadow-sm transition-all"
              :style="{ backgroundColor: editForm.background, color: editForm.foreground }"
            >{{ editForm.name || '预览' }}</span>
          </div>

          <!-- Name -->
          <div class="space-y-1.5">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">名称</label>
            <UInput v-model="editForm.name" placeholder="标签名称" />
          </div>

          <!-- Description -->
          <div class="space-y-1.5">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">描述</label>
            <UInput v-model="editForm.description" placeholder="可选的简短描述" />
          </div>

          <!-- Color -->
          <div class="space-y-1.5">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">颜色</label>
            <div class="flex items-center gap-4">
              <div class="flex items-center gap-2">
                <label class="relative w-8 h-8 rounded-lg cursor-pointer overflow-hidden shadow-sm ring-1 ring-gray-200 dark:ring-gray-700" :style="{ backgroundColor: editForm.background }">
                  <input type="color" v-model="editForm.background" class="absolute inset-0 opacity-0 cursor-pointer w-full h-full" />
                </label>
                <UInput v-model="editForm.background" size="sm" class="w-28" placeholder="#000000" />
              </div>
              <div class="flex items-center gap-2">
                <span class="text-xs text-gray-400">文字</span>
                <label class="relative w-8 h-8 rounded-lg cursor-pointer overflow-hidden shadow-sm ring-1 ring-gray-200 dark:ring-gray-700" :style="{ backgroundColor: editForm.foreground }">
                  <input type="color" v-model="editForm.foreground" class="absolute inset-0 opacity-0 cursor-pointer w-full h-full" />
                </label>
                <UInput v-model="editForm.foreground" size="sm" class="w-28" placeholder="#ffffff" />
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
            <UButton variant="outline" color="neutral" @click="cancelEditLabel">取消</UButton>
            <UButton :loading="labelSaving" :disabled="!editForm.name.trim()" @click="saveLabelEdit">保存</UButton>
          </div>
        </div>

        <!-- List view -->
        <div v-else class="p-5 space-y-3">
          <div class="flex items-center justify-end">
            <UButton size="sm" icon="i-heroicons-plus" @click="startAddLabel">新增标签</UButton>
          </div>

          <div class="space-y-0.5 max-h-[28rem] overflow-y-auto -mx-2">
            <div
              v-for="(props, name) in labelItems"
              :key="name"
              class="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/60 group transition-colors"
            >
              <div class="flex items-center gap-3 min-w-0">
                <span
                  class="px-2.5 py-0.5 rounded-full text-xs font-medium shrink-0"
                  :style="{ backgroundColor: props.background, color: props.foreground }"
                >{{ name }}</span>
                <span class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ props.description }}</span>
              </div>
              <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <UButton size="xs" variant="ghost" icon="i-heroicons-pencil-square" @click="startEditLabel(name as string)" />
                <UButton size="xs" variant="ghost" color="error" icon="i-heroicons-trash" @click="deleteLabel(name as string)" />
              </div>
            </div>
          </div>

          <div v-if="!Object.keys(labelItems).length" class="py-8 text-center text-sm text-gray-400">暂无标签</div>
        </div>
      </template>
    </UModal>

    <!-- 删除问题确认弹窗 -->
    <UModal v-model:open="showDeleteConfirm">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>删除问题</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showDeleteConfirm = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              确认删除问题 <span class="font-medium">#{{ issue.id }} {{ issue.title }}</span>？
            </p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showDeleteConfirm = false">取消</UButton>
            <UButton color="error" :loading="deleting" @click="handleDeleteIssue">确认删除</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- 「进行中」自动认领弹窗 -->
    <UModal v-model:open="showSelfAssignPrompt">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>设为进行中</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showSelfAssignPrompt = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">该问题还没有负责人，要同时把负责人设为你自己吗？</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="confirmSelfAssign(false)">仅修改状态</UButton>
            <UButton color="primary" @click="confirmSelfAssign(true)">是，由我处理</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>

  <div v-else class="text-center py-20 text-sm text-gray-400 dark:text-gray-500">问题不存在</div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

import { type CalendarDate, parseDate, type DateValue } from '@internationalized/date'
import { changeLines } from '~/utils/issueHistory'

const { api } = useApi()
const { can, hasGroup, user: authUser } = useAuth()
const isManager = computed(() =>
  hasGroup('管理员') || (authUser.value?.is_superuser ?? false)
)
const canEditEstimatedHours = isManager
const selfUserId = computed(() => Number(authUser.value?.id ?? 0))

type HistoryChange = { field: string; label: string; before: any; after: any }
type HistoryEntry = { id: number; type: '+' | '~' | '-'; date: string; user: string | null; changes: HistoryChange[] }

const historyLoading = ref(false)
const history = ref<HistoryEntry[]>([])

async function loadHistory() {
  if (!isManager.value) return
  historyLoading.value = true
  try {
    history.value = await api<HistoryEntry[]>(`/api/issues/${route.params.id}/history/`)
  } catch (e) {
    console.error('Failed to load issue history:', e)
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

// 右侧信息栏各卡片折叠状态:持久化到浏览器 localStorage,刷新后保持上次的展开/收起
type PanelKey = 'ai' | 'attrs' | 'info' | 'analysis' | 'attachments' | 'repo' | 'related' | 'github' | 'pr' | 'source' | 'assignments' | 'history'
const PANEL_STATE_KEY = 'issue-detail:panels'
const panelDefaults: Record<PanelKey, boolean> = {
  ai: true, attrs: true, info: true, analysis: false, attachments: true,
  repo: false, related: true, github: true, pr: true, source: true,
  assignments: false, history: true,
}
const panelOpen = reactive<Record<PanelKey, boolean>>({ ...panelDefaults })
if (import.meta.client) {
  try {
    const saved = JSON.parse(localStorage.getItem(PANEL_STATE_KEY) || '{}')
    for (const k of Object.keys(panelDefaults) as PanelKey[]) {
      if (typeof saved[k] === 'boolean') panelOpen[k] = saved[k]
    }
  } catch { /* 损坏的存储忽略,用默认值 */ }
  watch(panelOpen, v => localStorage.setItem(PANEL_STATE_KEY, JSON.stringify(v)), { deep: true })
}
function togglePanel(k: PanelKey) {
  panelOpen[k] = !panelOpen[k]
  // 变更历史首次展开时才拉取
  if (k === 'history' && panelOpen.history && !history.value.length) loadHistory()
}

function formatRelative(iso: string): string {
  const d = new Date(iso)
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString('zh-CN')
}

// 鼠标悬停时显示完整本地时间
function formatFullTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN')
}

const calendarValue = computed<DateValue | undefined>(() => {
  const v = form.value.estimated_completion
  if (!v) return undefined
  try { return parseDate(v) } catch { return undefined }
})

function onCalendarUpdate(value: unknown) {
  if (!value || Array.isArray(value)) {
    form.value.estimated_completion = ''
    autoSave('estimated_completion', null)
    return
  }
  const d = value as CalendarDate
  const iso = `${d.year}-${String(d.month).padStart(2, '0')}-${String(d.day).padStart(2, '0')}`
  form.value.estimated_completion = iso
  autoSave('estimated_completion', iso)
}
const route = useRoute()
const router = useRouter()
const { isOnline } = useServiceStatus()
const toast = useToast()

const loading = ref(true)
const issue = ref<any>(null)
const aiAnalyzing = ref(false)
const showDeleteConfirm = ref(false)
const deleting = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null
const analyses = ref<any[]>([])

async function fetchAnalyses() {
  if (!issue.value?.id) return
  analyses.value = await api<any[]>(`/api/issues/${issue.value.id}/analyses/`).catch(() => []) || []
}

async function handleDeleteIssue() {
  if (!issue.value) return
  deleting.value = true
  try {
    await api(`/api/issues/${issue.value.id}/`, { method: 'DELETE' })
    router.push('/app/issues')
  } catch (e) {
    console.error('Delete issue failed:', e)
  } finally {
    deleting.value = false
  }
}

function fieldLabel(field: string) {
  const labels: Record<string, string> = { cause: '原因分析', solution: '解决方案', remark: '备注' }
  return labels[field] || field
}

const latestAnalysis = computed(() => analyses.value[0] || null)
const latestAiCause = computed(() => {
  const done = analyses.value.find(a => a.status === 'done' && a.results?.cause)
  return done?.results?.cause || ''
})
const latestAiSolution = computed(() => {
  const done = analyses.value.find(a => a.status === 'done' && a.results?.solution)
  return done?.results?.solution || ''
})

import IssueComments from '~/components/issue/IssueComments.vue'
import MarkdownIt from 'markdown-it'
const md = new MarkdownIt({ html: false, linkify: true })
function renderMarkdown(text: string) {
  if (!text) return ''
  return md.render(text)
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (savedFieldTimer) clearTimeout(savedFieldTimer)
  // 卸载前若有待发的协助人保存,立即补发,避免快速离开页面丢失改动
  if (helpersSaveTimer) flushHelpersSave()
})
// 站点参照数据走 useReferenceData 会话级缓存(用户/开发者/项目/仓库/站点设置),
// 与问题列表页共享,避免每次进详情页重复拉取;developers 仅取「开发者」组。
const { siteSettings, users, developers, projects, repos, ensureSettings, ensureUsers, ensureProjects, ensureRepos } = useReferenceData()
const labelItems = computed<Record<string, { foreground: string; background: string; description: string }>>(() => siteSettings.value?.labels || {})

const showLabelPicker = ref(false)
const labelSearchQuery = ref('')
const showLabelManager = ref(false)
const editingLabel = ref<string | null>(null)
const editForm = ref({ name: '', foreground: '#ffffff', background: '#0075ca', description: '' })
const addingLabel = ref(false)
const labelSaving = ref(false)

function startEditLabel(name: string) {
  editingLabel.value = name
  addingLabel.value = false
  const lbl = labelItems.value[name]
  editForm.value = { name, foreground: lbl?.foreground ?? '#ffffff', background: lbl?.background ?? '#0075ca', description: lbl?.description ?? '' }
}

function startAddLabel() {
  addingLabel.value = true
  editingLabel.value = null
  editForm.value = { name: '', foreground: '#ffffff', background: '#0075ca', description: '' }
}

function cancelEditLabel() {
  editingLabel.value = null
  addingLabel.value = false
}

async function saveLabelEdit() {
  labelSaving.value = true
  try {
    const updated = { ...labelItems.value }
    if (editingLabel.value && editingLabel.value !== editForm.value.name) {
      delete updated[editingLabel.value]
    }
    updated[editForm.value.name] = {
      foreground: editForm.value.foreground,
      background: editForm.value.background,
      description: editForm.value.description,
    }
    const res = await api<any>('/api/settings/labels/', { method: 'PATCH', body: { labels: updated } })
    // 写回共享缓存,问题列表等其它页面同步生效
    siteSettings.value = { ...(siteSettings.value || {}), labels: res.labels }
    editingLabel.value = null
    addingLabel.value = false
  } catch (e) {
    console.error('Save label failed:', e)
  } finally {
    labelSaving.value = false
  }
}

async function deleteLabel(name: string) {
  labelSaving.value = true
  try {
    const updated = { ...labelItems.value }
    delete updated[name]
    const res = await api<any>('/api/settings/labels/', { method: 'PATCH', body: { labels: updated } })
    // 写回共享缓存,问题列表等其它页面同步生效
    siteSettings.value = { ...(siteSettings.value || {}), labels: res.labels }
  } catch (e) {
    console.error('Delete label failed:', e)
  } finally {
    labelSaving.value = false
  }
}

const filteredLabelNames = computed(() => {
  const names = Object.keys(labelItems.value)
  if (!labelSearchQuery.value) return names
  const q = labelSearchQuery.value.toLowerCase()
  return names.filter(n => n.toLowerCase().includes(q) || labelItems.value[n]?.description.toLowerCase().includes(q))
})
const allGHIssues = ref<any[]>([])
const linkedPRs = ref<PullRequestRow[]>([])
const suggestResolved = ref(false)
const descriptionEditor = ref<{ setMode: (m: 'edit' | 'preview') => void } | null>(null)

const isNewIssue = computed(() => !issue.value?.description && !issue.value?.title)

// 删除附件确认
const showDeleteAttachmentConfirm = ref(false)
const pendingDeleteAttachment = ref<{ id: string; file_url: string; file_name: string } | null>(null)

// GitHub 创建
const showCreateGH = ref(false)
const ghCreateRepo = ref('')
const ghCreating = ref(false)
const ghCreateError = ref('')

// GitHub 关联
const showLinkGH = ref(false)

// 关联 Issues — JSON 字段, 后端 detail serializer 已经 resolved 出 title/status
type RelatedItem = { id: number; title: string; status: string; priority?: string; kind: string; reason: string; added_at: string }
const relatedIssuesResolved = computed<RelatedItem[]>(() => (issue.value as any)?.related_issues_resolved || [])
const relatedSearchOpen = ref(false)
const relatedSearchQ = ref('')
const relatedSearching = ref(false)
const relatedSearchResults = ref<Array<{ id: number; title: string }>>([])
let relatedSearchTimer: ReturnType<typeof setTimeout> | null = null

function openRelatedSearch() {
  relatedSearchOpen.value = true
  relatedSearchQ.value = ''
  relatedSearchResults.value = []
}
function closeRelatedSearch() {
  relatedSearchOpen.value = false
  relatedSearchQ.value = ''
  relatedSearchResults.value = []
  if (relatedSearchTimer) { clearTimeout(relatedSearchTimer); relatedSearchTimer = null }
}
function onRelatedSearchInput(q: string) {
  if (relatedSearchTimer) clearTimeout(relatedSearchTimer)
  const query = (q || '').trim()
  if (!query) {
    relatedSearchResults.value = []
    return
  }
  // debounce 250ms 避免每键一次 API
  relatedSearchTimer = setTimeout(async () => {
    relatedSearching.value = true
    try {
      // 直接复用 issues 列表搜索 (search 参数); 排除当前 issue
      const res = await api<any>(`/api/issues/?search=${encodeURIComponent(query)}&page_size=10`)
      const all = (res?.results || res || []) as Array<{ id: number; title: string }>
      const linkedIds = new Set([
        issue.value?.id,
        ...relatedIssuesResolved.value.map(r => r.id),
      ])
      relatedSearchResults.value = all.filter(x => !linkedIds.has(x.id)).slice(0, 8)
    } catch {
      relatedSearchResults.value = []
    } finally {
      relatedSearching.value = false
    }
  }, 250)
}
async function addRelated(relatedId: number) {
  if (!issue.value?.id) return
  try {
    await api(`/api/issues/${issue.value.id}/related/`, {
      method: 'POST',
      body: { id: relatedId },
    })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    closeRelatedSearch()
  } catch (e) {
    console.error('Add related failed:', e)
  }
}
async function removeRelated(relatedId: number) {
  if (!issue.value?.id) return
  try {
    await api(`/api/issues/${issue.value.id}/related/${relatedId}/`, { method: 'DELETE' })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
  } catch (e) {
    console.error('Remove related failed:', e)
  }
}

// 外部来源: ai_wizard 是内部 AI 生成不算外部; 仅 github / external_api 等第三方接口
// 且 source_meta 含具体字段 (feedback_id / reporter / context / attachments) 时才有展示价值
const hasExternalSource = computed(() => {
  const issue_val: any = issue.value
  if (!issue_val) return false
  const src = issue_val.source
  if (!src || src === 'ai_wizard') return false
  const meta = issue_val.source_meta
  if (!meta || typeof meta !== 'object') return false
  return !!(
    meta.feedback_id
    || meta.reporter
    || meta.context
    || (Array.isArray(meta.attachments) && meta.attachments.length)
  )
})
const ghLinkRepoFilter = ref('')
const ghSelectedIds = ref<number[]>([])
const ghLinking = ref(false)

const repoOptions = computed(() => repos.value.map(r => ({ label: r.full_name, value: String(r.id) })))
const issueRepo = computed(() => {
  if (!issue.value?.repo) return null
  return repos.value.find(r => r.id === issue.value.repo) || null
})
const projectOptions = computed(() => projects.value.map(p => ({ label: p.name, value: String(p.id) })))
// 当前所选项目允许的仓库 — 仓库下拉只能在项目关联的仓库里选
const issueProjectRepoOptions = computed(() => {
  const pid = form.value.project
  if (!pid) return [] as { label: string; value: string }[]
  const project = projects.value.find(p => String(p.id) === String(pid))
  const repoIds: (string | number)[] = project?.repos || []
  const allowed = new Set(repoIds.map(String))
  return repos.value
    .filter(r => allowed.has(String(r.id)))
    .map(r => ({ label: r.full_name, value: String(r.id) }))
})

const linkedGHIds = computed(() => new Set((issue.value?.github_issues || []).map((g: any) => g.id)))

const availableGHIssues = computed(() => {
  return allGHIssues.value.filter(gh => {
    if (linkedGHIds.value.has(gh.id)) return false
    if (ghLinkRepoFilter.value && String(gh.repo) !== ghLinkRepoFilter.value) return false
    return true
  })
})

const form = ref({
  title: '',
  description: '',
  labels: [] as string[],
  assignee: '_none',
  helpers: [] as string[],
  remark: '',
  cause: '',
  solution: '',
  estimated_completion: '',
  estimated_hours: '',
  actual_hours: '',
  project: '' as string,
  repo: '' as string,
})

// 选中胶囊是主色实底,按主色亮度挑白/深字,保证浅主色(如纯黄)也可读
function chipTextOn(hex: string): string {
  const h = hex.length === 4 ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}` : hex
  const r = parseInt(h.slice(1, 3), 16) / 255
  const g = parseInt(h.slice(3, 5), 16) / 255
  const b = parseInt(h.slice(5, 7), 16) / 255
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.62 ? '#374151' : '#ffffff'
}

// 与列表页滑块一致:低→紧急排列;主色来自站点设置(usePriority),无主色档位用兜底灰
const configuredPriorities = usePriorityItems()
const priorityItems = computed(() => configuredPriorities.value.slice().reverse().map((p) => {
  const cssColor = isSafeHexColor(p.background) ? p.background : PRIORITY_FALLBACK_COLOR
  return { ...p, cssColor, textOn: chipTextOn(cssColor) }
}))
// 状态列表与主色来自站点设置(useStatus),statusMainColor 已做安全 hex 校验与兜底
const configuredStatuses = useStatusItems()
// 隐藏被禁用的状态;但工单当前状态若恰为被禁用状态(历史数据),仍保留该胶囊以正常回显并高亮
const statusItems = computed(() => configuredStatuses.value
  .filter(s => !s.disabled || s.value === issue.value?.status)
  .map((s) => {
    const cssColor = statusMainColor(s.value)
    return { ...s, cssColor, textOn: chipTextOn(cssColor) }
  }))
const assigneeItems = computed(() => {
  const items = [
    { label: '无', value: '_none' },
    ...developers.value.map(u => ({ label: u.name || u.username, value: String(u.id) })),
  ]
  // 当前负责人若不在开发者组(历史数据),仍保留其选项以正常回显已保存值
  const current = form.value.assignee
  if (current && current !== '_none' && !items.some(i => i.value === current)) {
    const u = users.value.find(x => String(x.id) === current)
    items.push({ label: u ? (u.name || u.username) : current, value: current })
  }
  return items
})
// 求助(协助人)不受开发者限制,仍可选全部用户
const helperItems = computed(() =>
  users.value.map(u => ({ label: u.name || u.username, value: String(u.id) }))
)

const savedForm = ref<typeof form.value>({ ...form.value })
const savingField = ref<string | null>(null)
// 失焦自动保存成功后，短暂显示"已保存"
const savedField = ref<string | null>(null)
let savedFieldTimer: ReturnType<typeof setTimeout> | null = null
function markSaved(field: string) {
  savedField.value = field
  if (savedFieldTimer) clearTimeout(savedFieldTimer)
  savedFieldTimer = setTimeout(() => {
    if (savedField.value === field) savedField.value = null
  }, 2000)
}

function isFieldDirty(field: keyof typeof form.value) {
  return JSON.stringify(form.value[field]) !== JSON.stringify(savedForm.value[field])
}

function populateForm(data: any) {
  form.value = {
    title: data.title || '',
    description: data.description || '',
    labels: data.labels || [],
    assignee: data.assignee ? String(data.assignee) : '_none',
    helpers: (data.helpers || []).map(String),
    remark: data.remark || '',
    cause: data.cause || '',
    solution: data.solution || '',
    estimated_completion: data.estimated_completion || '',
    estimated_hours: data.estimated_hours != null ? String(data.estimated_hours) : '',
    actual_hours: data.actual_hours != null ? String(data.actual_hours) : '',
    project: data.project != null ? String(data.project) : '',
    repo: data.repo != null ? String(data.repo) : '',
  }
  savedForm.value = JSON.parse(JSON.stringify(form.value))
}

async function fetchIssue() {
  issue.value = await api<any>(`/api/issues/${route.params.id}/`)
  populateForm(issue.value)
}

async function triggerAIAnalysis() {
  if (aiAnalyzing.value) return // prevent double-click
  aiAnalyzing.value = true
  try {
    const res = await api<any>(`/api/issues/${route.params.id}/ai-analyze/`, {
      method: 'POST',
    })
    pollAnalysisStatus(res.analysis_id)
  } catch (e: any) {
    const status = e.status || e.statusCode
    if (status === 409) {
      // Already running (likely auto-triggered), poll it
      const analysisId = e.data?.analysis_id
      if (analysisId) {
        pollAnalysisStatus(analysisId)
      } else {
        aiAnalyzing.value = false
      }
    } else {
      aiAnalyzing.value = false
    }
  }
}

function pollAnalysisStatus(analysisId: number | undefined) {
  if (!analysisId) { aiAnalyzing.value = false; return }
  let failCount = 0
  pollTimer = setInterval(async () => {
    try {
      const res = await api<any>(`/api/ai/analysis/${analysisId}/status/`)
      failCount = 0
      if (res.status === 'done' || res.status === 'failed') {
        clearInterval(pollTimer!)
        aiAnalyzing.value = false
        await fetchAnalyses()
      }
    } catch {
      failCount++
      if (failCount >= 3) {
        clearInterval(pollTimer!)
        aiAnalyzing.value = false
      }
    }
  }, 5000)
}



// 文本输入框：显示保存按钮，点击后保存
async function saveField(field: keyof typeof form.value) {
  if (!issue.value) return
  savingField.value = field
  try {
    const body: Record<string, any> = {}
    const val = form.value[field]
    if (field === 'actual_hours') body.actual_hours = val ? Number(val) : null
    else if (field === 'estimated_hours') body.estimated_hours = val ? Number(val) : null
    else body[field] = val
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
    if (field === 'description') descriptionEditor.value?.setMode('preview')
  } catch (e) {
    console.error(`Save ${field} failed:`, e)
  } finally {
    savingField.value = null
  }
}

// 文本框失焦自动保存：描述/备注/原因分析/解决方案，仅在有改动时提交。
// 只更新该字段的基线（不整表 refetch），避免覆盖其它正在编辑中的字段。
async function handleBlurSave(field: 'title' | 'description' | 'remark' | 'cause' | 'solution') {
  if (!issue.value || !isFieldDirty(field)) return
  savingField.value = field
  try {
    const value = form.value[field]
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body: { [field]: value } })
    savedForm.value[field] = JSON.parse(JSON.stringify(value))
    ;(issue.value as any)[field] = value
    if (field === 'description') descriptionEditor.value?.setMode('preview')
    markSaved(field)
  } catch (e) {
    console.error(`Auto-save ${field} failed:`, e)
  } finally {
    savingField.value = null
  }
}

// 下拉/胶囊/日期：直接保存
async function autoSave(field: string, rawValue: any) {
  if (!issue.value) return
  let value = rawValue
  if (field === 'assignee') value = rawValue === '_none' ? null : rawValue
  if (field === 'helpers') value = (rawValue as string[]).map(Number)
  if (field === 'estimated_completion') value = rawValue || null
  if (field === 'repo') value = rawValue ? Number(rawValue) : null
  try {
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body: { [field]: value } })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error(`Auto-save ${field} failed:`, e)
  }
}

// 协助人多选:trailing debounce(后沿防抖)。多选时用户会连续勾选多人,若每勾一次就 PATCH,
// 既多发请求,又在变更历史里留下多条碎片快照。改为收集改动、静默 HELPERS_SAVE_DELAY 后只发一次。
const HELPERS_SAVE_DELAY = 800
let helpersSaveTimer: ReturnType<typeof setTimeout> | null = null

// 协助人集合相对已保存基线是否有变化(顺序无关:仅比较成员集合,避免重排序触发空保存)
function helpersDirty(): boolean {
  const cur = [...form.value.helpers].map(String).sort()
  const base = [...savedForm.value.helpers].map(String).sort()
  return JSON.stringify(cur) !== JSON.stringify(base)
}

// v-model 已即时更新 form.helpers(UI 立即反映勾选);这里仅(重新)安排延迟保存
function onHelpersChange() {
  if (helpersSaveTimer) clearTimeout(helpersSaveTimer)
  helpersSaveTimer = setTimeout(flushHelpersSave, HELPERS_SAVE_DELAY)
}

async function flushHelpersSave() {
  if (helpersSaveTimer) { clearTimeout(helpersSaveTimer); helpersSaveTimer = null }
  if (!issue.value || !helpersDirty()) return
  savingField.value = 'helpers'
  try {
    const ids = form.value.helpers.map(Number)
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body: { helpers: ids } })
    savedForm.value.helpers = [...form.value.helpers]
    ;(issue.value as any).helpers = ids
    markSaved('helpers')
    if (panelOpen.history) loadHistory() // 历史面板已展开则刷新,立即看到本次变更
  } catch (e) {
    console.error('Auto-save helpers failed:', e)
  } finally {
    savingField.value = null
  }
}

// 切换项目时, 若原 repo 不在新项目的仓库列表里, 同 PATCH 清空 repo
async function onProjectChange(newProjectId: string) {
  if (!issue.value || !newProjectId) return
  const project = projects.value.find(p => String(p.id) === String(newProjectId))
  const newRepoIds = new Set<string>((project?.repos || []).map((r: any) => String(r)))
  const body: any = { project: Number(newProjectId) }
  if (issue.value.repo && !newRepoIds.has(String(issue.value.repo))) {
    body.repo = null
  }
  try {
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Project change failed:', e)
  }
}

function toggleLabel(lbl: string) {
  const idx = form.value.labels.indexOf(lbl)
  if (idx >= 0) form.value.labels.splice(idx, 1)
  else form.value.labels.push(lbl)
  autoSave('labels', [...form.value.labels])
}

// 优先级/状态胶囊直接保存
async function updateField(field: string, value: string) {
  await autoSave(field, value)
}

// 「进行中」自动认领弹窗状态
const showSelfAssignPrompt = ref(false)
const pendingStatus = ref('')

// 状态胶囊点击处理（已解决 -> 已关闭 时检查 GitHub；进行中且无负责人时询问认领）
function handleStatusClick(newStatus: string) {
  if (newStatus === '已关闭') {
    const hasOpenGH = issue.value?.github_issues?.some((gh: any) => gh.state === 'open')
    if (hasOpenGH) {
      closeWithGitHub()
      return
    }
  }
  // 改为「进行中」且当前无负责人 → 询问是否同时把负责人设为自己
  if (newStatus === '进行中' && form.value.assignee === '_none') {
    pendingStatus.value = newStatus
    showSelfAssignPrompt.value = true
    return
  }
  updateField('status', newStatus)
}

// 弹窗确认:alsoAssign 为 true 时同时把负责人设为当前用户
async function confirmSelfAssign(alsoAssign: boolean) {
  const targetStatus = pendingStatus.value
  showSelfAssignPrompt.value = false
  pendingStatus.value = ''
  if (!issue.value || !targetStatus) return
  const body: Record<string, any> = { status: targetStatus }
  if (alsoAssign) body.assignee = selfUserId.value
  try {
    await api(`/api/issues/${issue.value.id}/`, { method: 'PATCH', body })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Self-assign status change failed:', e)
  }
}

async function closeWithGitHub() {
  if (!issue.value) return
  try {
    await api(`/api/issues/${issue.value.id}/close-with-github/`, { method: 'POST' })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Close failed:', e)
  }
}

function toggleGHSelection(id: number) {
  const idx = ghSelectedIds.value.indexOf(id)
  if (idx >= 0) ghSelectedIds.value.splice(idx, 1)
  else ghSelectedIds.value.push(id)
}

async function handleCreateGH() {
  if (!ghCreateRepo.value) {
    ghCreateError.value = '请选择仓库'
    return
  }
  ghCreating.value = true
  ghCreateError.value = ''
  try {
    await api(`/api/issues/${issue.value.id}/github-create/`, {
      method: 'POST',
      body: { repo: ghCreateRepo.value },
    })
    showCreateGH.value = false
    ghCreateRepo.value = ''
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e: any) {
    ghCreateError.value = e?.data?.detail || 'GitHub 创建失败'
  } finally {
    ghCreating.value = false
  }
}

async function handleLinkGH() {
  if (!ghSelectedIds.value.length) return
  ghLinking.value = true
  try {
    await api(`/api/issues/${issue.value.id}/github-link/`, {
      method: 'POST',
      body: { github_issue_ids: ghSelectedIds.value },
    })
    showLinkGH.value = false
    ghSelectedIds.value = []
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Link failed:', e)
  } finally {
    ghLinking.value = false
  }
}

async function unlinkGitHubIssue(ghId: number) {
  try {
    await api(`/api/issues/${issue.value.id}/github-link/`, {
      method: 'DELETE',
      body: { github_issue_ids: [ghId] },
    })
    issue.value = await api<any>(`/api/issues/${route.params.id}/`)
    populateForm(issue.value)
  } catch (e) {
    console.error('Unlink failed:', e)
  }
}

// 关联弹窗用的 GitHub Issues 全量列表(后端无分页,返回整表)。改为打开「关联已有 Issue」
// 弹窗时才懒加载,并加 once 守卫,避免每次进详情页都全量拉取一份多数用不到的数据。
const ghIssuesLoaded = ref(false)
async function fetchGHIssues() {
  if (ghIssuesLoaded.value) return
  allGHIssues.value = await api<any[]>('/api/repos/github-issues/').catch(() => []) || []
  ghIssuesLoaded.value = true
}
function openLinkGH() {
  showLinkGH.value = true
  fetchGHIssues()
}

async function fetchLinkedPRs() {
  if (!issue.value?.id) return
  try {
    const res = await api<{ results: PullRequestRow[]; suggest_resolved: boolean }>(
      `/api/issues/${issue.value.id}/pull-requests/`
    )
    linkedPRs.value = res.results || []
    suggestResolved.value = !!res.suggest_resolved
  } catch (e) {
    console.error('Failed to load linked PRs:', e)
  }
}

// 采纳建议:走与状态胶囊相同的 PATCH 路径,完成后刷新 PR 区
async function acceptResolveSuggestion() {
  await autoSave('status', '已解决')
  await fetchLinkedPRs()
}

onMounted(async () => {
  // 具体 issue 必拉;用户/设置/仓库/项目走 useReferenceData 会话级缓存,与列表页共享,
  // 重复进入详情页不再重复请求。
  const [issueData] = await Promise.all([
    api<any>(`/api/issues/${route.params.id}/`).catch(() => null),
    ensureUsers(),
    ensureSettings(),
    ensureRepos(),
    ensureProjects(),
  ])
  issue.value = issueData
  setPrioritiesFromSettings(siteSettings.value?.priorities)
  setStatusesFromSettings(siteSettings.value?.issue_statuses)
  if (issueData) populateForm(issueData)
  loading.value = false
  // GitHub Issues 全量列表改为打开「关联已有 Issue」弹窗时懒加载(见 openLinkGH)
  fetchLinkedPRs()
  // 检查是否有正在运行的 AI 分析，恢复轮询
  checkRunningAnalysis()
  fetchAnalyses()
  loadHistory()
})

async function checkRunningAnalysis() {
  if (!issue.value?.id) return
  try {
    const res = await api<any>(`/api/issues/${issue.value.id}/ai-status/`)
    if (res?.analysis_id && res?.status === 'running') {
      aiAnalyzing.value = true
      pollAnalysisStatus(res.analysis_id)
    }
  } catch {
    // No running analysis endpoint or no analysis — that's fine
  }
}

// 关联附件
const attachmentInputRef = ref<HTMLInputElement | null>(null)
const attachments = computed(() => (issue.value as any)?.attachments ?? [])
const imageAttachments = computed(() => attachments.value.filter((a: any) => a.mime_type?.startsWith('image/')))
const fileAttachments = computed(() => attachments.value.filter((a: any) => !a.mime_type?.startsWith('image/')))

async function handleUploadComplete(uploaded: { url: string; filename: string; id: string }) {
  if (!issue.value?.id) return
  const { api } = useApi()
  try {
    await api(`/api/issues/${issue.value.id}/attachments/`, {
      method: 'POST',
      body: { attachment_id: uploaded.id },
    })
    issue.value = await api<any>(`/api/issues/${issue.value.id}/`)
  } catch {
    // 绑定失败静默处理
  }
}

// Mirror this allowlist with backend/apps/tools/views.py and MarkdownEditor.vue.
const ATTACHMENT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
const ATTACHMENT_ALLOWED_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/gif', 'image/webp',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/plain', 'text/markdown', 'text/csv', 'application/json',
  'application/zip', 'application/x-zip-compressed',
  'text/html',
])
const ATTACHMENT_EXTENSION_FALLBACK = new Set(['md', 'txt', 'csv', 'json', 'zip', 'html', 'htm'])
const ATTACHMENT_MAX_IMAGE_SIZE = 5 * 1024 * 1024
const ATTACHMENT_MAX_FILE_SIZE = 20 * 1024 * 1024

async function handleAttachmentSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  const { api } = useApi()
  for (const file of files) {
    const allowedByType = ATTACHMENT_ALLOWED_TYPES.has(file.type)
    const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
    const allowedByExt = ATTACHMENT_EXTENSION_FALLBACK.has(ext)
    if (!allowedByType && !allowedByExt) {
      toast.add({ title: `不支持的文件类型: ${file.type || file.name}`, color: 'error' })
      continue
    }
    const isImg = ATTACHMENT_IMAGE_TYPES.has(file.type)
    const limit = isImg ? ATTACHMENT_MAX_IMAGE_SIZE : ATTACHMENT_MAX_FILE_SIZE
    if (file.size > limit) {
      const label = isImg ? '图片' : '文件'
      const limitMb = isImg ? 5 : 20
      toast.add({ title: `${label} ${file.name} 超过 ${limitMb}MB 限制`, color: 'error' })
      continue
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api<{ url: string; filename: string; id: string }>('/api/tools/upload/image/', {
        method: 'POST',
        body: formData,
      })
      await handleUploadComplete(res)
    } catch (e: any) {
      const detail = e?.data?.detail || `上传失败: ${file.name}`
      toast.add({ title: detail, color: 'error' })
    }
  }
}

function promptDeleteAttachment(att: { id: string; file_url: string; file_name: string }) {
  pendingDeleteAttachment.value = att
  showDeleteAttachmentConfirm.value = true
}

async function deleteAttachment(attachmentId: string, removeFromDescription = false) {
  const { api } = useApi()
  try {
    await api(`/api/tools/attachments/${attachmentId}/`, { method: 'DELETE' })
    if (issue.value) {
      const att = (issue.value as any).attachments.find((a: any) => a.id === attachmentId)
      if (removeFromDescription && att) {
        removeAttachmentFromDescription(att.file_url)
      }
      ;(issue.value as any).attachments = (issue.value as any).attachments.filter((a: any) => a.id !== attachmentId)
    }
  } catch {
    // 删除失败静默处理
  }
}

function removeAttachmentFromDescription(fileUrl: string) {
  if (!form.value.description) return
  const escaped = fileUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  form.value.description = form.value.description
    .replace(new RegExp(`!\\[[^\\]]*\\]\\(${escaped}\\)`, 'g'), '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function insertAttachmentToDescription(attachment: any) {
  form.value.description = (form.value.description || '') + `\n![${attachment.file_name}](${attachment.file_url})`
}

function assignmentActionLabel(a: string): string {
  return ({
    claim: '认领',
    assign: '指派',
    ai_assign: 'AI 分配',
    transfer: '转单',
    confirm: '确认',
  } as Record<string, string>)[a] || a
}

function formatAssignmentDate(s: string): string {
  return new Date(s).toLocaleString('zh-CN')
}
</script>

<style scoped>
/* 优先级/状态胶囊按站点设置主色(--chip)着色,深浅用 color-mix 派生(同列表页行/卡片)。
   未选中:弱底+灰调字;选中:深底+深字+2px 描边+加粗,选中/未选中需一眼可辨 */
.option-chip {
  background-color: color-mix(in srgb, var(--chip) 9%, #ffffff);
  color: color-mix(in srgb, var(--chip) 40%, #9ca3af);
}
.option-chip:hover {
  background-color: color-mix(in srgb, var(--chip) 20%, #ffffff);
}
:root.dark .option-chip {
  background-color: color-mix(in srgb, var(--chip) 14%, #111827);
  color: color-mix(in srgb, var(--chip) 40%, #6b7280);
}
:root.dark .option-chip:hover {
  background-color: color-mix(in srgb, var(--chip) 26%, #111827);
}
/* 选中:主色实底+亮度自适应字色(--chip-text 由 chipTextOn 算出)+留缝外圈光环 */
.option-chip-active {
  font-weight: 600;
  background-color: var(--chip);
  color: var(--chip-text, #ffffff);
  box-shadow: 0 0 0 2px #ffffff, 0 0 0 3.5px color-mix(in srgb, var(--chip) 60%, #d1d5db);
}
:root.dark .option-chip-active {
  background-color: var(--chip);
  color: var(--chip-text, #ffffff);
  box-shadow: 0 0 0 2px #111827, 0 0 0 3.5px color-mix(in srgb, var(--chip) 70%, #4b5563);
}
.form-row { display: flex; flex-direction: column; gap: 0.375rem; }
.form-row label { font-size: 0.8125rem; font-weight: 500; color: #374151; }
:root.dark .form-row label { color: #9ca3af; }
.form-row :deep(input),
.form-row :deep(textarea),
.form-row :deep(select),
.form-row :deep(button[role="combobox"]),
.form-row :deep([data-part="trigger"]) { width: 100% !important; }
.form-grid-2 { display: grid; grid-template-columns: 1fr; gap: 1rem; }
@media (min-width: 768px) {
  .form-grid-2 { grid-template-columns: 1fr 1fr; }
}
.modal-form { padding: 1.5rem 2rem; }
.modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
.modal-header h3 { font-size: 1.125rem; font-weight: 600; color: #111827; }
:root.dark .modal-header h3 { color: #f3f4f6; }
.modal-body { display: flex; flex-direction: column; gap: 1rem; }
.modal-footer { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #f3f4f6; }
:root.dark .modal-footer { border-top-color: #374151; }
.ai-progress-bar {
  width: 30%;
  animation: ai-progress 2s ease-in-out infinite;
}
@keyframes ai-progress {
  0% { margin-left: 0%; width: 20%; }
  50% { margin-left: 40%; width: 40%; }
  100% { margin-left: 80%; width: 20%; }
}
</style>
