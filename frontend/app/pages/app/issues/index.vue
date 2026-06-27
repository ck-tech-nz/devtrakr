<template>
  <!-- 看板模式定高(学 GitHub Projects):页面不滚动,列内独立滚动;手机端改为单列竖排,整页滚动 -->
  <div :class="viewMode === 'kanban' && !isMobile ? 'h-full min-h-0 flex flex-col gap-6' : 'space-y-6'">
    <MyPendingTasks />
    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-end">
      <!-- 工具栏控件整体居右 -->
      <div class="flex items-center justify-between md:justify-end gap-2 md:gap-3">
        <!-- 移动端:搜索常驻 + 其余筛选条件折叠进底部抽屉(见下方 UDrawer),避免窄屏工具栏拥挤 -->
        <UInput v-model="searchQuery" placeholder="搜索标题或编号" icon="i-heroicons-magnifying-glass" size="sm" class="flex-1 min-w-0 md:hidden" />
        <UButton
          class="md:hidden shrink-0"
          icon="i-heroicons-adjustments-horizontal"
          size="sm"
          variant="outline"
          color="neutral"
          @click="filterOpen = true"
        >
          筛选
          <UBadge v-if="activeFilterCount" color="primary" variant="solid" class="ml-1 rounded-full px-1.5 min-w-[1.125rem] justify-center leading-none">
            {{ activeFilterCount }}
          </UBadge>
        </UButton>

        <!-- 桌面端筛选控件:常驻内联(display:contents 融入工具栏);移动端隐藏,改由上方「筛选」抽屉操作 -->
        <div class="hidden md:contents">
          <!-- 筛选控件:常驻显示,不自动隐藏 -->
          <!-- 「查看全部」控制列表视图是否含已完成工单;看板视图改用「列编辑器」按状态列显隐 -->
          <label v-if="viewMode === 'table'" class="flex items-center gap-1.5 cursor-pointer select-none">
          <span class="text-sm text-gray-500 dark:text-gray-400">查看全部</span>
          <USwitch v-model="showCompleted" size="lg" />
        </label>
        <UInput v-model="searchQuery" placeholder="搜索标题或编号" icon="i-heroicons-magnifying-glass" size="sm" class="w-44" />
        <!-- 「只看我的」与「负责人」同属处理人筛选,合并为一个连体按钮组 -->
        <UButtonGroup size="sm">
          <UButton
            icon="i-heroicons-user"
            :variant="onlyMine ? 'solid' : 'outline'"
            :color="onlyMine ? 'primary' : 'neutral'"
            @click="onlyMine = !onlyMine"
          >
            只看我的
          </UButton>
          <USelect :model-value="filterAssignee" :items="filterAssigneeOptions" class="w-24" value-key="value" placeholder="负责人" @update:model-value="(v: string) => filterAssignee = v === '_all' ? '' : v" />
        </UButtonGroup>
        <!-- 「只看我提出的」与「提出人」同属提出人筛选(按创建人 created_by),合并为一个连体按钮组 -->
        <UButtonGroup size="sm">
          <UButton
            icon="i-heroicons-user-circle"
            :variant="onlyMineReported ? 'solid' : 'outline'"
            :color="onlyMineReported ? 'primary' : 'neutral'"
            @click="onlyMineReported = !onlyMineReported"
          >
            只看我提出的
          </UButton>
          <USelect :model-value="filterReporterUser" :items="filterReporterOptions" class="w-24" value-key="value" placeholder="提出人" @update:model-value="(v: string) => setReporterUser(v)" />
        </UButtonGroup>
        <PrioritySlider v-model="filterPriority" />
        <div class="relative">
          <USelect v-model="filterStatus" :items="filterStatusOptions" size="sm" class="w-24" value-key="value" placeholder="状态" />
          <button v-if="filterStatus" class="filter-clear" @click="filterStatus = ''">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </div>

        <!-- 始终可见:点击徽章触发的上下文标签(处理人/优先级/提出人) -->
        <UBadge v-if="filterHandler" variant="subtle" size="md" class="filter-chip shrink-0">
          <span>处理人：{{ filterHandler.label }}</span>
          <button class="ml-1 flex items-center" aria-label="清除处理人筛选" @click="filterHandler = null">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </UBadge>
        <UBadge
          v-if="filterPriorityTag" :color="priorityColor(filterPriorityTag.value)" variant="subtle" size="md"
          class="shrink-0" :class="priorityBadgeClass(filterPriorityTag.value)" :style="priorityBadgeStyle(filterPriorityTag.value)"
        >
          <span>优先级：{{ filterPriorityTag.label }}</span>
          <button class="ml-1 flex items-center" aria-label="清除优先级筛选" @click="filterPriorityTag = null">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </UBadge>
        <UBadge v-if="filterReporter" variant="subtle" size="md" class="filter-chip shrink-0">
          <span>提出人：{{ filterReporter.label }}</span>
          <button class="ml-1 flex items-center" aria-label="清除提出人筛选" @click="filterReporter = null">
            <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
          </button>
        </UBadge>
        </div>

        <!-- 始终可见:视图切换 / 刷新 / 新建 -->
        <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
          <button
            class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
            :class="viewMode === 'kanban' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="viewMode = 'kanban'"
          >
            看板
          </button>
          <button
            class="px-3 py-1 text-sm font-medium rounded-md transition-colors"
            :class="viewMode === 'table' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="viewMode = 'table'"
          >
            列表
          </button>
        </div>
        <UButton
          icon="i-heroicons-arrow-path"
          size="sm"
          variant="ghost"
          color="neutral"
          :loading="loading"
          aria-label="刷新"
          @click="fetchIssues"
        />
        <UButton icon="i-heroicons-plus" size="sm" @click="openCreateModal">
          <span class="hidden md:inline">新建</span>
        </UButton>
        <!-- 看板列显示/隐藏编辑器:置于工具栏行尾,仅看板视图显示 -->
        <KanbanColumnEditor
          v-if="viewMode === 'kanban'"
          :statuses="kanbanEditorStatuses"
          :hidden="settings.issues_kanban_hidden"
          @update:hidden="(v: string[]) => updateSettings('issues_kanban_hidden', v)"
        />
      </div>
    </div>

    <!-- 移动端筛选抽屉:聚合处理人/提出人/优先级/状态等筛选,搜索框仍常驻工具栏 -->
    <UDrawer
      :open="filterOpen"
      title="筛选"
      description="筛选问题列表"
      :ui="{
        content: 'bg-white/90 dark:bg-slate-900/90 backdrop-blur-[20px] backdrop-saturate-[180%]',
        overlay: 'bg-black/30',
        title: 'sr-only',
        description: 'sr-only',
      }"
      @update:open="filterOpen = $event"
    >
      <template #content>
        <div class="px-4 pt-1 pb-4 space-y-5">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">筛选</h3>
            <UButton v-if="activeFilterCount" variant="ghost" color="neutral" size="xs" @click="clearAllFilters">
              清除全部
            </UButton>
          </div>

          <!-- 查看全部(仅列表视图):是否含已完成工单 -->
          <label v-if="viewMode === 'table'" class="flex items-center justify-between gap-3 cursor-pointer select-none">
            <span class="text-sm text-gray-700 dark:text-gray-300">查看全部(含已完成)</span>
            <USwitch v-model="showCompleted" size="lg" />
          </label>

          <!-- 处理人:只看我的 + 负责人下拉 -->
          <div class="space-y-2">
            <span class="block text-xs font-medium text-gray-500 dark:text-gray-400">处理人</span>
            <div class="flex items-stretch gap-2">
              <UButton
                class="flex-1 justify-center"
                icon="i-heroicons-user"
                :variant="onlyMine ? 'solid' : 'outline'"
                :color="onlyMine ? 'primary' : 'neutral'"
                @click="onlyMine = !onlyMine"
              >
                只看我的
              </UButton>
              <USelect :model-value="filterAssignee" :items="filterAssigneeOptions" class="flex-1" value-key="value" placeholder="负责人" @update:model-value="(v: string) => filterAssignee = v === '_all' ? '' : v" />
            </div>
          </div>

          <!-- 提出人:只看我提出的 + 提出人下拉 -->
          <div class="space-y-2">
            <span class="block text-xs font-medium text-gray-500 dark:text-gray-400">提出人</span>
            <div class="flex items-stretch gap-2">
              <UButton
                class="flex-1 justify-center"
                icon="i-heroicons-user-circle"
                :variant="onlyMineReported ? 'solid' : 'outline'"
                :color="onlyMineReported ? 'primary' : 'neutral'"
                @click="onlyMineReported = !onlyMineReported"
              >
                只看我提出的
              </UButton>
              <USelect :model-value="filterReporterUser" :items="filterReporterOptions" class="flex-1" value-key="value" placeholder="提出人" @update:model-value="(v: string) => setReporterUser(v)" />
            </div>
          </div>

          <!-- 优先级 -->
          <div class="space-y-2">
            <span class="block text-xs font-medium text-gray-500 dark:text-gray-400">优先级</span>
            <PrioritySlider v-model="filterPriority" class="!w-full" />
          </div>

          <!-- 状态 -->
          <div class="space-y-2">
            <span class="block text-xs font-medium text-gray-500 dark:text-gray-400">状态</span>
            <div class="relative">
              <USelect v-model="filterStatus" :items="filterStatusOptions" size="sm" class="w-full" value-key="value" placeholder="全部状态" />
              <button v-if="filterStatus" class="filter-clear" @click="filterStatus = ''">
                <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
              </button>
            </div>
          </div>

          <!-- 已应用的上下文筛选(点击列表单元格触发):处理人/优先级/提出人 -->
          <div v-if="filterHandler || filterPriorityTag || filterReporter" class="flex flex-wrap gap-2">
            <UBadge v-if="filterHandler" variant="subtle" size="md" class="filter-chip">
              <span>处理人：{{ filterHandler.label }}</span>
              <button class="ml-1 flex items-center" aria-label="清除处理人筛选" @click="filterHandler = null">
                <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
              </button>
            </UBadge>
            <UBadge
              v-if="filterPriorityTag" :color="priorityColor(filterPriorityTag.value)" variant="subtle" size="md"
              :class="priorityBadgeClass(filterPriorityTag.value)" :style="priorityBadgeStyle(filterPriorityTag.value)"
            >
              <span>优先级：{{ filterPriorityTag.label }}</span>
              <button class="ml-1 flex items-center" aria-label="清除优先级筛选" @click="filterPriorityTag = null">
                <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
              </button>
            </UBadge>
            <UBadge v-if="filterReporter" variant="subtle" size="md" class="filter-chip">
              <span>提出人：{{ filterReporter.label }}</span>
              <button class="ml-1 flex items-center" aria-label="清除提出人筛选" @click="filterReporter = null">
                <UIcon name="i-heroicons-x-mark" class="w-3 h-3" />
              </button>
            </UBadge>
          </div>

          <UButton block size="lg" class="mt-1" @click="filterOpen = false">
            完成
          </UButton>
        </div>
        <div style="height: env(safe-area-inset-bottom)" />
      </template>
    </UDrawer>

    <!-- Create Issue Modal -->
    <UModal :open="showCreateModal" title="新建问题" :ui="{ content: 'sm:max-w-[960px]' }" @update:open="onCreateModalUpdate">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>新建问题</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="closeCreateModal" />
          </div>
          <div class="modal-body">
            <div class="form-row">
              <label>项目</label>
              <USelect v-model="newIssue.project" :items="projectOptions" placeholder="选择项目" value-key="value" />
            </div>
            <div v-if="projectRepos.length > 1" class="form-row">
              <label>关联仓库</label>
              <USelect v-model="newIssue.repo" :items="projectRepoOptions" placeholder="选择仓库" value-key="value" />
            </div>
            <div class="form-row">
              <label>标题 <span class="text-red-400">*</span></label>
              <UInput v-model="newIssue.title" placeholder="输入问题标题" @blur="runDuplicateCheck" />
              <div v-if="dupChecking || dupCandidates.length" class="dup-check-box">
                <p v-if="dupChecking" class="text-xs text-gray-500 dark:text-gray-400">
                  正在检查相似问题…
                </p>
                <div v-else>
                  <p class="text-sm text-amber-700 dark:text-amber-300 font-medium">
                    发现 {{ dupCandidates.length }} 条相似的未关闭问题，请确认是否重复：
                  </p>
                  <ul class="mt-1.5 space-y-1.5">
                    <li v-for="c in dupCandidates" :key="c.id" class="text-sm">
                      <div class="flex items-center gap-1.5">
                        <NuxtLink
                          :to="`/app/issues/${c.id}`"
                          target="_blank"
                          class="text-crystal-600 dark:text-crystal-400 hover:underline"
                        >
                          #{{ c.id }} {{ c.title }}
                        </NuxtLink>
                        <UBadge :color="statusColor(c.status)" variant="subtle" size="xs">{{ c.status }}</UBadge>
                      </div>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ c.reason }}</p>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div class="form-row">
              <label>描述</label>
              <MarkdownEditor
                v-model="newIssue.description"
                placeholder="详细描述问题"
                @upload-complete="handleCreateUploadComplete"
                @blur="runDuplicateCheck"
              />
            </div>
            <div class="form-grid-2">
              <div class="form-row">
                <label>优先级</label>
                <USelect v-model="newIssue.priority" :items="createPriorityOptions" value-key="value" />
              </div>
              <div class="form-row">
                <label>状态</label>
                <USelect v-model="newIssue.status" :items="createStatusOptions" value-key="value" />
              </div>
            </div>
            <div class="form-grid-2">
              <div class="form-row">
                <label>标签</label>
                <USelectMenu v-model="newIssue.labels" :items="labelOptions" multiple placeholder="选择标签" />
              </div>
              <div class="form-row">
                <label>负责人</label>
                <USelect v-model="newIssue.assignee" :items="createAssigneeOptions" placeholder="选择负责人" value-key="value" />
              </div>
            </div>
            <div class="form-row">
              <label>提出人</label>
              <UInput v-model="newIssue.reporter" placeholder="提出人姓名" />
            </div>
            <p v-if="createError" class="text-sm text-red-500">{{ createError }}</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="closeCreateModal">取消</UButton>
            <UButton :loading="creating" @click="handleCreateIssue">创建</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Batch Actions -->
    <div v-if="selectedRowsData.length > 0" class="hidden md:flex bg-crystal-50 dark:bg-crystal-950 rounded-xl border border-crystal-100 dark:border-crystal-800 p-3 items-center justify-between">
      <span class="text-sm text-crystal-700 dark:text-crystal-300">已选择 {{ selectedRowsData.length }} 项</span>
      <div class="flex items-center space-x-2">
        <UDropdownMenu :items="batchAssignItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">批量分配</UButton>
        </UDropdownMenu>
        <UDropdownMenu :items="batchPriorityItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">修改优先级</UButton>
        </UDropdownMenu>
        <UDropdownMenu :items="batchStatusItems" :content="{ align: 'end' as const }">
          <UButton size="xs" color="primary" variant="outline">修改状态</UButton>
        </UDropdownMenu>
        <UButton v-if="can('issues.delete_issue')" size="xs" color="error" variant="outline" @click="showBatchDeleteConfirm = true">批量删除</UButton>
      </div>
    </div>

    <!-- 批量删除确认弹窗 -->
    <UModal v-model:open="showBatchDeleteConfirm">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>批量删除</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="showBatchDeleteConfirm = false" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              确认删除选中的 <span class="font-medium">{{ selectedRowsData.length }}</span> 个问题？
            </p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="showBatchDeleteConfirm = false">取消</UButton>
            <UButton color="error" :loading="batchDeleting" @click="handleBatchDelete">确认删除</UButton>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <!-- Mobile Card List -->
    <div v-else-if="isMobile && viewMode === 'table'" class="space-y-2">
      <IssueCard v-for="issue in issues" :key="issue.id" :issue="issue" @changed="fetchIssues" @request-transfer="openTransfer($event)" />
      <div class="flex items-center justify-between pt-2">
        <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ totalCount }} 条</span>
        <div class="flex items-center space-x-2">
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page <= 1" @click="page--">上一页</UButton>
          <span class="text-xs text-gray-500 dark:text-gray-400">{{ page }} / {{ totalPages }}</span>
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page >= totalPages" @click="page++">下一页</UButton>
        </div>
      </div>
    </div>

    <!-- Kanban View -->
    <SharedKanbanBoard
      v-else-if="viewMode === 'kanban'"
      class="flex-1 min-h-0"
      :columns="kanbanColumns"
      :item-key="(item: any) => item.id"
      :card-class="kanbanCardClass"
      :card-style="kanbanCardStyle"
      scrollable
      @drop="onKanbanDrop"
      @load-more="kanban.loadMore"
    >
      <template #card="{ item }">
        <IssueKanbanCard :item="item" />
      </template>
    </SharedKanbanBoard>

    <!-- Table View -->
    <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200/80 dark:border-gray-700 shadow-sm overflow-hidden">
      <div class="flex justify-end px-4 py-2 border-b border-gray-50 dark:border-gray-800">
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <USwitch v-model="showGHColumn" size="xs" />
          <span class="text-xs text-gray-500 dark:text-gray-400">GitHub Issues</span>
        </label>
      </div>
      <UTable
        v-model:row-selection="rowSelection"
        :data="issues"
        :columns="columns"
        class="issues-table"
        :style="{ '--title-col-w': titleColWidth ? titleColWidth + 'px' : '' }"
        :ui="{ th: 'text-xs whitespace-nowrap', td: 'text-sm', tr: 'hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer' }"
        @select="onRowSelect"
      >
        <template #select-header="{ table }">
          <UCheckbox
            :model-value="table.getIsAllPageRowsSelected()"
            @update:model-value="(v: boolean) => table.toggleAllPageRowsSelected(!!v)"
          />
        </template>
        <template #select-cell="{ row }">
          <UCheckbox
            :model-value="row.getIsSelected()"
            @update:model-value="(v: boolean) => row.toggleSelected(!!v)"
          />
        </template>
        <template #id-header>
          <IssueSortHeader label="ID" :dir="sortDir('id')" @toggle="toggleSort('id')" />
        </template>
        <template #id-cell="{ row }">
          <NuxtLink :to="`/app/issues/${row.original.id}`" class="text-crystal-500 dark:text-crystal-400 hover:text-crystal-700 dark:hover:text-crystal-300 font-medium">{{ row.original.id }}</NuxtLink>
        </template>
        <template #title-header>
          <div class="title-header">
            <IssueSortHeader label="标题" :dir="sortDir('title')" @toggle="toggleSort('title')" />
            <span
              class="col-resize-handle"
              title="拖动调整列宽，双击复原"
              @pointerdown="onTitleResizeDown"
              @dblclick.stop="resetTitleColWidth"
              @click.stop
            ><i></i><i></i></span>
          </div>
        </template>
        <template #title-cell="{ row }">
          <div class="flex items-center gap-1.5 min-w-0">
            <UBadge v-if="row.original.source" color="info" variant="subtle" size="xs" class="shrink-0">外部</UBadge>
            <EditableCell class="min-w-0" :value="row.original.title" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'title', v)" />
          </div>
        </template>
        <template #priority-header>
          <IssueSortHeader label="优先级" :dir="sortDir('priority')" @toggle="toggleSort('priority')" />
        </template>
        <template #priority-cell="{ row }">
          <!-- data-priority 供行级 :has() 选择器按优先级给整行着色 -->
          <UBadge
            :color="priorityColor(row.original.priority)" variant="subtle" size="sm"
            class="cursor-pointer hover:opacity-80"
            :class="priorityBadgeClass(row.original.priority)"
            :style="priorityBadgeStyle(row.original.priority)"
            :data-priority="row.original.priority"
            :title="`筛选优先级：${priorityLabel(row.original.priority)}`"
            @click.stop="filterByPriority(row.original)"
          >{{ priorityLabel(row.original.priority) }}</UBadge>
        </template>
        <template #status-header>
          <IssueSortHeader label="状态" :dir="sortDir('status')" @toggle="toggleSort('status')" />
        </template>
        <template #status-cell="{ row }">
          <StatusCell
            :issue="row.original"
            :self-user-id="selfUserId"
            @changed="fetchIssues"
            @request-transfer="openTransfer(row.original)"
            @request-assign="openAssign(row.original)"
          />
        </template>
        <template #reporter-cell="{ row }">
          <button
            v-if="row.original.reporter || row.original.created_by_name"
            class="block truncate text-left hover:text-crystal-600 dark:hover:text-crystal-400 hover:underline"
            :title="`筛选提出人：${row.original.reporter || row.original.created_by_name}`"
            @click.stop="filterByReporter(row.original)"
          >{{ row.original.reporter || row.original.created_by_name }}</button>
          <span v-else class="block truncate text-gray-300 dark:text-gray-600">-</span>
        </template>
        <template #cause-cell="{ row }">
          <EditableCell :value="row.original.cause" :placeholder="row.original.ai_cause" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'cause', v)" />
        </template>
        <template #solution-cell="{ row }">
          <EditableCell :value="row.original.solution" :placeholder="row.original.ai_solution" @dblclick="cancelRowClick" @save="(v: string) => inlineUpdate(row.original.id, 'solution', v)" />
        </template>
        <template #created_at-header>
          <IssueSortHeader label="历时" :dir="sortDir('created_at')" @toggle="toggleSort('created_at')" />
        </template>
        <template #created_at-cell="{ row }">
          <div class="duration-cell">
            <div class="duration-bar">
              <div
                class="duration-fill"
                :class="{ 'duration-overdue': issueDuration(row.original).pct > 100 }"
                :style="{
                  width: Math.min(issueDuration(row.original).pct, 100) + '%',
                  backgroundColor: issueDuration(row.original).color,
                }"
              />
            </div>
            <span class="duration-label" :style="{ color: issueDuration(row.original).color }">
              {{ issueDuration(row.original).label }}
            </span>
          </div>
        </template>
        <template #estimated_completion-header>
          <IssueSortHeader label="要求完成日期" :dir="sortDir('estimated_completion')" @toggle="toggleSort('estimated_completion')" />
        </template>
        <template #estimated_completion-cell="{ row }">
          {{ row.original.estimated_completion ? row.original.estimated_completion.slice(5) : '-' }}
        </template>
        <template #github_issues-cell="{ row }">
          <div v-if="row.original.github_issues?.length" class="flex flex-wrap gap-1">
            <NuxtLink
              v-for="gh in row.original.github_issues"
              :key="gh.id"
              :to="`/app/repos/${gh.repo}/issues/${gh.id}`"
              class="text-xs text-crystal-500 dark:text-crystal-400 hover:underline"
            >#{{ gh.github_id }}</NuxtLink>
          </div>
          <span v-else class="text-gray-300 dark:text-gray-600">-</span>
        </template>
      </UTable>
      <div class="flex items-center justify-between px-4 py-3 border-t border-gray-50 dark:border-gray-800">
        <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ totalCount }} 条</span>
        <div class="flex items-center space-x-2">
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page <= 1" @click="page--">上一页</UButton>
          <span class="text-xs text-gray-500 dark:text-gray-400">{{ page }} / {{ totalPages }}</span>
          <UButton size="xs" variant="ghost" color="neutral" :disabled="page >= totalPages" @click="page++">下一页</UButton>
        </div>
      </div>
    </div>

    <TransferDialog
      v-if="transferDialog.issueId !== null && transferDialog.projectId !== null"
      v-model="transferDialog.open"
      :issue-id="transferDialog.issueId"
      :project-id="transferDialog.projectId"
      :self-user-id="selfUserId"
      @transferred="fetchIssues"
    />
    <AssignDialog
      v-if="assignDialog.issueId !== null && assignDialog.projectId !== null"
      v-model="assignDialog.open"
      :issue-id="assignDialog.issueId"
      :project-id="assignDialog.projectId"
      @assigned="fetchIssues"
    />
  </div>
</template>

<script setup lang="ts">
import { ISSUE_STATUS, ISSUE_STATUS_OPTIONS, KANBAN_DEFAULT_COLUMNS, KANBAN_COMPLETED_LEFT, KANBAN_COMPLETED_RIGHT, statusColor as statusColorFn } from '~/constants/issueStatus'
import StatusCell from '~/components/issue/StatusCell.vue'
import KanbanColumnEditor from '~/components/issue/KanbanColumnEditor.vue'
import TransferDialog from '~/components/issue/TransferDialog.vue'
import AssignDialog from '~/components/issue/AssignDialog.vue'
import { buildIssueQueryParams, buildIssueFilterParams } from '~/utils/issueQuery'

definePageMeta({ layout: 'default' })

const { api } = useApi()
const { user, can } = useAuth()
const { isMobile } = useMobile()

const selfUserId = computed(() => Number(user.value?.id ?? 0))

// 优先级档位(含管理员配置的主色),onMounted 拉到站点设置后更新
const priorityItems = usePriorityItems()

// 表格行按优先级着色:主色管理员可配,无法静态枚举,按配置动态生成规则注入 <head>
const priorityRowCss = computed(() => priorityItems.value
  .filter(p => isSafeHexColor(p.background) && /^[\w-]+$/.test(p.value))
  .map((p) => {
    const sel = `.issues-table tbody tr:has([data-priority="${p.value}"])`
    const c = p.background
    return [
      `${sel} { background-color: color-mix(in srgb, ${c} 7%, #ffffff); }`,
      `${sel}:hover { background-color: color-mix(in srgb, ${c} 14%, #ffffff); }`,
      `:root.dark ${sel} { background-color: color-mix(in srgb, ${c} 22%, transparent); }`,
      `:root.dark ${sel}:hover { background-color: color-mix(in srgb, ${c} 32%, transparent); }`,
    ].join('\n')
  })
  .join('\n'))
useHead({ style: [{ innerHTML: priorityRowCss }] })

const transferDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})
const assignDialog = ref<{ open: boolean; issueId: number | null; projectId: number | null }>({
  open: false, issueId: null, projectId: null,
})

function openTransfer(issue: any) {
  transferDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}
function openAssign(issue: any) {
  assignDialog.value = { open: true, issueId: issue.id, projectId: issue.project }
}

// 点击提出人：有 reporter 文本则按该文本精确筛选；为空时列回退显示创建人,
// 按「显示的提出人=该创建人」筛选(reporter_display_user),与下拉/按钮同一口径
function filterByReporter(issue: any) {
  if (issue.reporter) {
    filterReporter.value = { type: 'reporter', value: issue.reporter, label: issue.reporter }
  } else if (issue.created_by) {
    filterReporter.value = { type: 'reporter_display_user', value: String(issue.created_by), label: issue.created_by_name || '创建人' }
  }
}

// 点击优先级徽章：以独立标签筛选；同时清空优先级下拉，避免双重筛选
function filterByPriority(issue: any) {
  if (!issue.priority) return
  filterPriority.value = ''
  filterPriorityTag.value = { value: issue.priority, label: priorityLabel(issue.priority) }
}
const { settings, update: updateSettings } = useUserSettings()
const route = useRoute()
const toast = useToast()

const viewMode = computed({
  get: () => settings.value.issues_view_mode,
  set: (v: 'kanban' | 'table') => updateSettings('issues_view_mode', v),
})
// 「查看全部」持久化到浏览器 localStorage,刷新页面不丢失该偏好
const SHOW_COMPLETED_KEY = 'issues:showCompleted'
const showCompleted = ref(
  typeof localStorage !== 'undefined' && localStorage.getItem(SHOW_COMPLETED_KEY) === '1',
)

// 标题列宽:拖拽调整 + 按浏览器 localStorage 记忆(见 useColumnWidth)
const {
  width: titleColWidth,
  load: loadTitleColWidth,
  startResize: startTitleResize,
  reset: resetTitleColWidth,
} = useColumnWidth('issues:title-col-width')

// 表头手柄按下:以当前列实际像素宽为起点开始拖拽
function onTitleResizeDown(e: PointerEvent) {
  const th = (e.currentTarget as HTMLElement | null)?.closest('th')
  startTitleResize(e, th?.getBoundingClientRect().width ?? 0)
}

const page = ref(1)
const pageSize = 15

// Filters：初始值从 URL query 读取，使外部链接（如首页统计卡片）可预填筛选条件
const filterAssignee = ref<string>(typeof route.query.assignee === 'string' ? route.query.assignee : '')
const filterPriority = ref<string>(typeof route.query.priority === 'string' ? route.query.priority : '')
const filterStatus = ref<string>(typeof route.query.status === 'string' ? route.query.status : '')
const searchQuery = ref<string>(typeof route.query.search === 'string' ? route.query.search : '')
// 提出人筛选：点击非空 reporter 按文本匹配(type 'reporter');下拉/按钮/空 reporter 行
// 按「显示的提出人=某用户」匹配(type 'reporter_display_user',含 reporter 空回退创建人)
const filterReporter = ref<{ type: 'reporter' | 'created_by' | 'reporter_display_user'; value: string; label: string } | null>(null)
// 处理人筛选：点击状态徽章触发，按 assignee 筛选，以独立标签展示
const filterHandler = ref<{ id: string; label: string } | null>(null)
// 优先级筛选：点击优先级徽章触发，以独立标签展示
const filterPriorityTag = ref<{ value: string; label: string } | null>(null)
// 「只看我的」：等价于 assignee=当前用户;与负责人下拉互斥
const onlyMine = ref(false)
// 「只看我提出的」：等价于 created_by=当前用户;与提出人下拉互斥
const onlyMineReported = ref(false)

// 移动端筛选抽屉开关 + 已激活筛选计数(处理人/提出人/优先级/状态四组),供「筛选」按钮角标显示
const filterOpen = ref(false)
const activeFilterCount = computed(() => {
  let n = 0
  if (onlyMine.value || filterAssignee.value || filterHandler.value) n++
  if (onlyMineReported.value || filterReporter.value) n++
  if (filterPriority.value || filterPriorityTag.value) n++
  if (filterStatus.value) n++
  return n
})
// 一键清除全部筛选(搜索框常驻不受影响);互斥 watcher 自动收尾,批处理后仅触发一次取数
function clearAllFilters() {
  onlyMine.value = false
  filterAssignee.value = ''
  onlyMineReported.value = false
  filterReporter.value = null
  filterHandler.value = null
  filterPriority.value = ''
  filterPriorityTag.value = null
  filterStatus.value = ''
}

const rowSelection = ref<Record<string, boolean>>({})
const showBatchDeleteConfirm = ref(false)
const batchDeleting = ref(false)

const loading = ref(true)
const issues = ref<any[]>([])
const analyzingIssueIds = ref<Set<number>>(new Set())
const totalCount = ref(0)
const users = ref<any[]>([])
// 负责人候选:仅「开发者」用户组成员(提出人/求助等仍用完整 users)
const developers = ref<any[]>([])
const labelOptions = ref<string[]>([])
const projects = ref<any[]>([])
const repos = ref<any[]>([])

// Create issue modal state
const { confirm: showConfirm } = useDialog()
const showCreateModal = ref(false)

function openCreateModal() {
  if (!newIssue.value.project && user.value?.default_project) {
    newIssue.value.project = String(user.value.default_project.id)
  }
  showCreateModal.value = true
}

async function onCreateModalUpdate(v: boolean) {
  if (v) {
    showCreateModal.value = true
    return
  }
  if (hasFormContent()) {
    const ok = await showConfirm({
      title: '放弃编辑？',
      message: '表单中有未保存的内容，关闭后将丢失。确定要放弃吗？',
      confirmText: '放弃',
      cancelText: '继续编辑',
      color: 'error',
    })
    if (!ok) return
  }
  resetCreateForm()
  showCreateModal.value = false
}
const creating = ref(false)
const createError = ref('')
const defaultAssignee = computed(() => '_none')
const newIssue = ref({
  project: '',
  title: '',
  description: '',
  priority: 'P2',
  status: ISSUE_STATUS.UNASSIGNED,
  labels: [] as string[],
  assignee: defaultAssignee.value,
  repo: null as string | null,
  reporter: user.value?.name || '',
})

// Duplicate-check state for the create-issue modal.
const dupChecking = ref(false)
const dupCandidates = ref<Array<{ id: number; title: string; status: string; reason: string }>>([])
const dupCheckedKey = ref('')

function dupCheckKey(): string {
  const p = newIssue.value.project || ''
  const t = newIssue.value.title.trim().toLowerCase()
  const d = (newIssue.value.description || '').trim().toLowerCase()
  return `${p}|${t}|${d}`
}

async function runDuplicateCheck() {
  const projectId = newIssue.value.project
  const title = newIssue.value.title.trim()
  if (!projectId || title.length < 3) {
    dupCandidates.value = []
    return
  }
  const key = dupCheckKey()
  if (key === dupCheckedKey.value) return
  dupCheckedKey.value = key
  dupChecking.value = true
  try {
    const res = await api<{ candidates: Array<{ id: number; title: string; status: string; reason: string }> }>(
      '/api/issues/check-duplicate/',
      {
        method: 'POST',
        body: {
          project: projectId,
          title,
          description: newIssue.value.description || '',
        },
        format: 'json',
      },
    )
    // Discard stale responses if the user edited the form mid-call.
    if (dupCheckKey() === key) dupCandidates.value = res.candidates || []
  } catch {
    dupCandidates.value = []
  } finally {
    dupChecking.value = false
  }
}

function hasFormContent(): boolean {
  const n = newIssue.value
  return !!(
    n.title.trim()
    || n.description.trim()
    || n.project
    || n.labels.length > 0
    || attachmentIds.value.length > 0
    || n.repo
    || n.priority !== 'P2'
    || n.status !== ISSUE_STATUS.UNASSIGNED
    || n.assignee !== '_none'
  )
}

function resetCreateForm() {
  newIssue.value = {
    project: String(user.value?.default_project?.id || ''),
    title: '',
    description: '',
    priority: 'P2',
    status: ISSUE_STATUS.UNASSIGNED,
    labels: [],
    assignee: defaultAssignee.value,
    repo: null,
    reporter: user.value?.name || '',
  }
  attachmentIds.value = []
  projectRepos.value = []
  dupCandidates.value = []
  dupCheckedKey.value = ''
  dupChecking.value = false
}

const attachmentIds = ref<string[]>([])

const projectRepos = ref<any[]>([])

watch(() => newIssue.value.project, (projectId) => {
  if (!projectId) {
    projectRepos.value = []
    newIssue.value.repo = null
    return
  }
  const project = projects.value.find(p => String(p.id) === String(projectId))
  const repoIds: string[] = (project?.repos || []).map((r: any) => String(r))
  projectRepos.value = repos.value.filter(r => repoIds.includes(String(r.id)))
  if (projectRepos.value.length === 1) {
    newIssue.value.repo = String(projectRepos.value[0].id)
  } else {
    newIssue.value.repo = null
  }
})

watch([() => newIssue.value.title, () => newIssue.value.description], () => {
  dupCandidates.value = []
  dupCheckedKey.value = ''
})

const projectRepoOptions = computed(() => projectRepos.value.map(r => ({ label: r.name, value: String(r.id) })))

const projectOptions = computed(() => projects.value.map(p => ({ label: p.name, value: String(p.id) })))
const createPriorityOptions = computed(() => priorityItems.value.map(p => ({ label: `${p.value} ${p.label}`, value: p.value })))
// 状态选项 label 走站点配置(statusLabel),value 是流转逻辑依赖的固定值;隐藏被禁用的状态
const createStatusOptions = computed(() => ISSUE_STATUS_OPTIONS.filter(o => !isStatusDisabled(o.value)).map(o => ({ value: o.value, label: statusLabel(o.value) })))
const createAssigneeOptions = computed(() => [{ label: '无', value: '_none' }, ...developers.value.map(u => ({ label: u.name || u.username, value: String(u.id) }))])

// 首项「全部负责人」用于清除负责人筛选；SelectItem 不允许空字符串 value，用 '_all' 哨兵在模板里映射回 ''
// 负责人候选限「开发者」组(developers)
const filterAssigneeOptions = computed(() => [
  { label: '全部负责人', value: '_all' },
  ...developers.value.map(u => ({ label: u.name || u.username, value: String(u.id) })),
])

// 提出人下拉：按「列里显示的提出人=某用户」筛选(reporter_display_user),选项与负责人同源(系统用户)
const filterReporterOptions = computed(() => [
  { label: '全部提出人', value: '_all' },
  ...users.value.map(u => ({ label: u.name || u.username, value: String(u.id) })),
])
// 下拉回显：仅当按「显示的提出人=某用户」筛选时回填;reporter 文本筛选(点击非空单元格)时留空占位
const filterReporterUser = computed(() =>
  filterReporter.value?.type === 'reporter_display_user' ? filterReporter.value.value : '',
)
function setReporterUser(v: string) {
  if (!v || v === '_all') {
    filterReporter.value = null
    return
  }
  const u = users.value.find(x => String(x.id) === v)
  filterReporter.value = { type: 'reporter_display_user', value: v, label: u?.name || u?.username || '提出人' }
}
const filterStatusOptions = computed(() => ISSUE_STATUS_OPTIONS.filter(o => !isStatusDisabled(o.value)).map(o => ({ value: o.value, label: statusLabel(o.value) })))

function closeCreateModal() {
  onCreateModalUpdate(false)
}

function handleCreateUploadComplete(uploaded: { url: string; filename: string; id: string }) {
  attachmentIds.value.push(uploaded.id)
}

async function handleCreateIssue() {
  if (!newIssue.value.title.trim()) {
    createError.value = '标题不能为空'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const body: any = {
      title: newIssue.value.title,
      description: newIssue.value.description,
      priority: newIssue.value.priority,
      status: newIssue.value.status,
      labels: newIssue.value.labels,
      attachment_ids: attachmentIds.value,
    }
    if (newIssue.value.project) body.project = newIssue.value.project
    if (newIssue.value.assignee && newIssue.value.assignee !== '_none') body.assignee = newIssue.value.assignee
    if (newIssue.value.repo) body.repo = newIssue.value.repo
    if (newIssue.value.reporter) body.reporter = newIssue.value.reporter
    const created = await api<any>('/api/issues/', { method: 'POST', body, format: 'json' })
    const msg = created?.assignee
      ? `已创建，分配给 ${created.assignee_name || '该成员'}`
      : '已创建，等待人工认领'
    toast.add({ title: msg, color: 'success' })
    resetCreateForm()
    showCreateModal.value = false
    await fetchIssues()
  } catch (e: any) {
    createError.value = formatApiError(e, '创建失败，请重试')
  } finally {
    creating.value = false
  }
}

const selectedRowsData = computed(() => {
  return Object.entries(rowSelection.value)
    .filter(([_, selected]) => selected)
    .map(([idx]) => issues.value[parseInt(idx)])
    .filter(Boolean)
})

const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize)))

const showGHColumn = ref(false)

// 列表排序:点击表头三态切换(无 → 升 → 降 → 无)。数据为后端分页,排序须走后端
// (否则只排当前页),通过 DRF OrderingFilter 的 ordering 参数实现。
// 列 → 后端字段映射;invert 表示该列的「升/降」与后端字段方向相反:
//   历时(created_at)越长 ⇔ created_at 越早,故「历时升序」= created_at 降序。
const SORT_FIELDS: Record<string, { field: string; invert?: boolean }> = {
  id: { field: 'id' },
  title: { field: 'title' },
  priority: { field: 'priority' },
  status: { field: 'status_order' },
  created_at: { field: 'created_at', invert: true },
  estimated_completion: { field: 'estimated_completion' },
}

const sortBy = ref<{ key: string; dir: 'asc' | 'desc' } | null>(null)

// 当前列的排序方向,供表头组件渲染指示图标
function sortDir(key: string): 'asc' | 'desc' | null {
  return sortBy.value?.key === key ? sortBy.value.dir : null
}

function toggleSort(key: string) {
  if (sortBy.value?.key !== key) {
    sortBy.value = { key, dir: 'asc' }
  } else if (sortBy.value.dir === 'asc') {
    sortBy.value = { key, dir: 'desc' }
  } else {
    sortBy.value = null
  }
}

const ordering = computed(() => {
  if (!sortBy.value) return ''
  const cfg = SORT_FIELDS[sortBy.value.key]
  if (!cfg) return ''
  const ascending = cfg.invert ? sortBy.value.dir === 'desc' : sortBy.value.dir === 'asc'
  return (ascending ? '' : '-') + cfg.field
})

const columns = computed(() => {
  const cols = [
    { id: 'select', header: '', cell: '' },
    { accessorKey: 'id', header: 'ID' },
    { accessorKey: 'title', header: '标题' },
    { accessorKey: 'cause', header: '原因分析' },
    { accessorKey: 'solution', header: '解决方案' },
    { accessorKey: 'priority', header: '优先级' },
    { accessorKey: 'status', header: '状态' },
    { accessorKey: 'reporter', header: '提出人' },
    { accessorKey: 'created_at', header: '历时' },
    { accessorKey: 'estimated_completion', header: '要求完成日期' },
  ]
  if (showGHColumn.value) {
    cols.push({ accessorKey: 'github_issues', header: 'GitHub Issues' })
  }
  return cols
})

// 看板按列独立取数(学 GitHub Projects):每列 20 条起,滚动到底续取。
// 列参数 = 当前筛选条件 + 该列状态;状态下拉筛了别的状态时该列置空不取数。
const kanban = useKanbanIssues((status, pageNum) => {
  if (filterStatus.value && filterStatus.value !== status) return null
  const p = buildIssueFilterParams({
    filterStatus: status,
    filterAssignee: filterAssignee.value,
    filterHandlerId: filterHandler.value?.id ?? null,
    filterPriority: filterPriority.value,
    filterPriorityTagValue: filterPriorityTag.value?.value ?? null,
    filterReporter: filterReporter.value,
    search: searchQuery.value,
  })
  p.set('page', String(pageNum))
  p.set('page_size', String(KANBAN_COLUMN_PAGE_SIZE))
  return p
})

// 看板候选列(完整顺序),排除管理员禁用的状态 —— 供列编辑器选择显隐
const kanbanCandidateKeys = computed(() =>
  [...KANBAN_COMPLETED_LEFT, ...KANBAN_DEFAULT_COLUMNS, ...KANBAN_COMPLETED_RIGHT]
    .filter(key => !isStatusDisabled(key)))
// 列编辑器选项:候选状态 + 显示名/主色
const kanbanEditorStatuses = computed(() => kanbanCandidateKeys.value.map(key => ({
  value: key,
  label: statusLabel(key),
  color: statusMainColor(key),
})))
// 实际渲染的看板列 = 候选列去掉用户隐藏的(被禁用的已在候选阶段排除;隐藏的列不拉取)
const kanbanStatusKeys = computed(() =>
  kanbanCandidateKeys.value.filter(key => !settings.value.issues_kanban_hidden.includes(key)))

const kanbanColumns = computed(() => kanbanStatusKeys.value.map((key) => {
  const col = kanban.columns.value[key]
  return {
    key,
    label: statusLabel(key),
    color: statusMainColor(key),
    items: col?.items ?? [],
    count: col?.count ?? 0,
    hasMore: col?.hasMore ?? false,
    loading: col?.loading ?? false,
  }
}))

async function onKanbanDrop({ itemId, fromColumn, toColumn }: { itemId: string | number; fromColumn: string; toColumn: string }) {
  // 乐观迁移,失败回滚
  const rollback = kanban.moveCard(itemId, fromColumn, toColumn)
  const moved = kanban.columns.value[toColumn]?.items.find((i: any) => i.id === itemId)
  if (moved) moved.status = toColumn
  try {
    await api(`/api/issues/${itemId}/`, {
      method: 'PATCH',
      body: { status: toColumn },
    })
  } catch (e) {
    console.error('Failed to update issue status:', e)
    if (moved) moved.status = fromColumn
    rollback()
  }
}

// 卡片底色随优先级升高变暖(默认低=白底/中=黄/高=橙/紧急=红),主色可在站点设置配置
function kanbanCardClass(item: any): string {
  return priorityCardClass(item.priority)
}
function kanbanCardStyle(item: any): Record<string, string> | undefined {
  return priorityCardStyle(item.priority)
}

let rowClickTimer: ReturnType<typeof setTimeout> | null = null
function onRowSelect(row: any, e?: Event) {
  if (!e) return
  const target = e.target as HTMLElement
  // Ignore clicks on checkboxes, buttons, links, and active inputs
  if (target.closest('input, button, a')) return
  // Delay navigation so double-click can cancel it
  if (rowClickTimer) clearTimeout(rowClickTimer)
  rowClickTimer = setTimeout(() => {
    navigateTo(`/app/issues/${row.original.id}`)
  }, 250)
}
function cancelRowClick() {
  if (rowClickTimer) { clearTimeout(rowClickTimer); rowClickTimer = null }
}

async function inlineUpdate(issueId: string, field: string, value: string) {
  try {
    await api(`/api/issues/${issueId}/`, {
      method: 'PATCH',
      body: { [field]: value },
    })
    // Update locally without full refetch
    const issue = issues.value.find((i: any) => i.id === issueId)
    if (issue) issue[field] = value
  } catch (e) {
    console.error('Inline update failed:', e)
    await fetchIssues()
  }
}

function formatApiError(e: any, fallback: string): string {
  const data = e?.data || e?.response?._data
  if (data && typeof data === 'object') {
    const msgs = Object.entries(data)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
      .join('; ')
    if (msgs) return msgs
  }
  return e?.message || fallback
}

function issueDuration(issue: any): { pct: number; color: string; label: string } {
  if (!issue.created_at) return { pct: 0, color: '#9ca3af', label: '-' }
  const now = Date.now()
  const start = new Date(issue.created_at).getTime()
  const elapsed = now - start
  const hours = elapsed / 3600000

  const deadline = issue.estimated_completion
    ? new Date(issue.estimated_completion).getTime()
    : start + 3 * 86400000 // 默认3天
  const total = deadline - start
  const pct = total > 0 ? Math.round((elapsed / total) * 100) : 100

  // 颜色: ≤50% 绿, ≤80% 黄, >80% 红
  const color = pct <= 50 ? '#22c55e' : pct <= 80 ? '#f59e0b' : '#ef4444'

  // 标签
  let label: string
  if (hours < 24) {
    label = `${Math.max(1, Math.round(hours))}h`
  } else {
    const days = (hours / 24).toFixed(1).replace(/\.0$/, '')
    label = `${days}d`
  }
  if (issue.estimated_completion) label += ` / ${issue.estimated_completion.slice(5)}`

  return { pct, color, label }
}

const statusColor = statusColorFn

// 请求序号:快速拖动优先级滑块等会连发多个请求,响应可能乱序到达。
// 只采纳最新一次请求的响应,丢弃过期响应,避免列表停在上一个筛选条件。
let fetchSeq = 0
async function fetchIssues() {
  // 看板模式:按列独立分页取数,列内有各自的加载态,不占用全局 loading。
  // 仍要递增 fetchSeq,作废在途的表格响应,防止其落地覆盖 issues/totalCount
  if (viewMode.value === 'kanban') {
    fetchSeq++
    loading.value = false
    await kanban.reset(kanbanStatusKeys.value)
    return
  }
  const seq = ++fetchSeq
  loading.value = true
  try {
    const params = buildIssueQueryParams({
      page: page.value,
      pageSize,
      showCompleted: showCompleted.value,
      filterStatus: filterStatus.value,
      filterAssignee: filterAssignee.value,
      filterHandlerId: filterHandler.value?.id ?? null,
      filterPriority: filterPriority.value,
      filterPriorityTagValue: filterPriorityTag.value?.value ?? null,
      filterReporter: filterReporter.value,
      search: searchQuery.value,
      ordering: ordering.value,
    })

    const data = await api<any>(`/api/issues/?${params.toString()}`)
    if (seq !== fetchSeq) return // 已有更新的请求发出,丢弃这个过期响应
    issues.value = data.results || data || []
    totalCount.value = data.count ?? issues.value.length
  } catch (e) {
    if (seq !== fetchSeq) return
    console.error('Failed to load issues:', e)
  } finally {
    if (seq === fetchSeq) loading.value = false
  }
}

async function batchUpdate(action: string, value: string) {
  const ids = selectedRowsData.value.map((row: any) => row.id)
  if (!ids.length) return
  try {
    await api('/api/issues/batch-update/', {
      method: 'POST',
      body: { ids, action, value },
    })
    rowSelection.value = {}
    await fetchIssues()
  } catch (e) {
    console.error('Batch update failed:', e)
  }
}

async function handleBatchDelete() {
  const ids = selectedRowsData.value.map((row: any) => row.id)
  if (!ids.length) return
  batchDeleting.value = true
  try {
    await api('/api/issues/batch-update/', {
      method: 'POST',
      body: { ids, action: 'delete' },
    })
    showBatchDeleteConfirm.value = false
    rowSelection.value = {}
    await fetchIssues()
  } catch (e) {
    console.error('Batch delete failed:', e)
  } finally {
    batchDeleting.value = false
  }
}

const batchAssignItems = computed(() => [developers.value.map(u => ({
  label: u.name || u.username,
  onSelect: () => batchUpdate('assign', String(u.id)),
}))])

const batchPriorityItems = computed(() => [priorityItems.value.map(p => ({
  label: `${p.value} ${p.label}`,
  onSelect: () => batchUpdate('priority', p.value),
}))])

const batchStatusItems = computed(() => [filterStatusOptions.value.map(s => ({
  label: s.label,
  onSelect: () => batchUpdate('set_status', s.value),
}))])

watch(page, () => {
  rowSelection.value = {}
  fetchIssues()
})

// 看板按列独立分页、表格按页取数,两种视图查询形态不同,切换时重新拉取
watch(viewMode, () => {
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

watch(showCompleted, (v) => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(SHOW_COMPLETED_KEY, v ? '1' : '0')
  }
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

// 列编辑器改动后,看板模式需重新拉取可见列(新显示的列需要取数;隐藏的列自动不再渲染)
watch(() => settings.value.issues_kanban_hidden, () => {
  if (viewMode.value === 'kanban') fetchIssues()
})

// 从负责人下拉框选值时清除处理人标签（两者都按 assignee 筛选，互斥）
watch(filterAssignee, (v) => {
  if (v) filterHandler.value = null
  if (v !== String(selfUserId.value)) onlyMine.value = false
})
watch(onlyMine, (on) => {
  if (on) {
    filterHandler.value = null
    filterAssignee.value = String(selfUserId.value)
  } else if (filterAssignee.value === String(selfUserId.value)) {
    filterAssignee.value = ''
  }
})
// 「只看我提出的」⇄ 提出人(显示的提出人=我) 双向同步
watch(onlyMineReported, (on) => {
  if (on) {
    filterReporter.value = {
      type: 'reporter_display_user',
      value: String(selfUserId.value),
      label: user.value?.name || user.value?.username || '我',
    }
  } else if (filterReporter.value?.type === 'reporter_display_user' && filterReporter.value.value === String(selfUserId.value)) {
    filterReporter.value = null
  }
})
// 提出人筛选不再指向「显示的提出人=我」时(下拉选了他人/清空/点击了 reporter 文本),取消按钮高亮
watch(filterReporter, (v) => {
  if (!(v?.type === 'reporter_display_user' && v.value === String(selfUserId.value))) {
    onlyMineReported.value = false
  }
})
// 从优先级下拉框选值时清除优先级标签（互斥）
watch(filterPriority, (v) => {
  if (v) filterPriorityTag.value = null
})

watch([filterAssignee, filterPriority, filterStatus, filterReporter, filterHandler, filterPriorityTag], () => {
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

// 排序变化回到第 1 页重新取数(后端排序,跨全部分页生效)
watch(sortBy, () => {
  page.value = 1
  rowSelection.value = {}
  fetchIssues()
})

let searchDebounce: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    rowSelection.value = {}
    fetchIssues()
  }, 300)
})

onUnmounted(() => {
  if (searchDebounce) clearTimeout(searchDebounce)
})

onMounted(async () => {
  loadTitleColWidth()
  // 站点设置先行:看板初次 reset 依赖 kanbanStatusKeys,必须先拿到状态禁用配置才能排除被禁用的列
  const settingsData = await api<any>('/api/settings/').catch(() => ({ labels: [] }))
  const rawLabels = settingsData?.labels || {}
  labelOptions.value = typeof rawLabels === 'object' && !Array.isArray(rawLabels) ? Object.keys(rawLabels) : rawLabels
  setPrioritiesFromSettings(settingsData?.priorities)
  setStatusesFromSettings(settingsData?.issue_statuses)
  const [, usersData, projectsData, reposData] = await Promise.all([
    fetchIssues(),
    api<any[]>('/api/users/choices/').catch(() => []),
    api<any>('/api/projects/').catch(() => ({ results: [] })),
    api<any>('/api/repos/').catch(() => ({ results: [] })),
  ])
  users.value = usersData || []
  // 「开发者」组从全量 choices 客户端筛出,省去单独的 ?group=开发者 调用
  developers.value = (usersData || []).filter((u: any) => u.groups?.includes('开发者'))
  projects.value = projectsData?.results || projectsData || []
  repos.value = reposData?.results || reposData || []
  // Check AI analysis status for issues with repos
  checkAnalyzingIssues()
})

async function checkAnalyzingIssues() {
  // 批量查询:一次请求拿到所有「正在分析」的工单 id,取代逐条 ai-status 的 N+1
  const ids = issues.value.filter(i => i.repo).map(i => i.id)
  if (!ids.length) {
    analyzingIssueIds.value = new Set()
    return
  }
  const data = await api<{ running_ids: number[] }>(
    `/api/issues/ai-status/?ids=${ids.join(',')}`
  ).catch(() => ({ running_ids: [] }))
  analyzingIssueIds.value = new Set<number>(data.running_ids || [])
}
</script>

<style scoped>
.modal-form {
  padding: 1.5rem 2rem;
  max-height: 90vh;
  overflow-y: auto;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}
.modal-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #111827;
}
:root.dark .modal-header h3 {
  color: #f3f4f6;
}
.modal-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.form-row label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: #374151;
}
:root.dark .form-row label {
  color: #9ca3af;
}
.form-row :deep(input),
.form-row :deep(textarea),
.form-row :deep(select),
.form-row :deep(button[role="combobox"]),
.form-row :deep([data-part="trigger"]) {
  width: 100% !important;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}
@media (min-width: 768px) {
  .form-grid-2 {
    grid-template-columns: 1fr 1fr;
  }
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #f3f4f6;
}
:root.dark .modal-footer {
  border-top-color: #374151;
}
/* 筛选标签(提出人/处理人/优先级):统一使用品牌色 crystal,避免 primary(绿) 与 CTA 撞色 */
.filter-chip {
  background-color: var(--color-crystal-50);
  color: var(--color-crystal-700);
  box-shadow: inset 0 0 0 1px var(--color-crystal-200);
}
:root.dark .filter-chip {
  background-color: color-mix(in oklab, var(--color-crystal-950) 60%, transparent);
  color: var(--color-crystal-300);
  box-shadow: inset 0 0 0 1px var(--color-crystal-800);
}
.filter-clear {
  position: absolute;
  right: 2rem;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  border-radius: 9999px;
  color: #9ca3af;
  cursor: pointer;
}
.filter-clear:hover {
  color: #374151;
  background-color: #f3f4f6;
}
:root.dark .filter-clear:hover {
  color: #d1d5db;
  background-color: #374151;
}
.duration-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 72px;
}
.duration-bar {
  height: 6px;
  border-radius: 3px;
  background-color: #f3f4f6;
  overflow: hidden;
}
:root.dark .duration-bar {
  background-color: #374151;
}
.duration-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}
.duration-overdue {
  animation: pulse-bar 2s ease-in-out infinite;
}
.duration-label {
  font-size: 11px;
  line-height: 1;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.dup-check-box {
  margin-top: 0.5rem;
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  background-color: #fffbeb; /* amber-50 */
  border: 1px solid #fde68a; /* amber-200 */
}
:root.dark .dup-check-box {
  background-color: rgba(120, 53, 15, 0.25); /* amber-900/25 */
  border-color: rgba(245, 158, 11, 0.4); /* amber-500/40 */
}
/*
 * Issues table: fixed layout so we control column widths.
 * Columns: select | ID | 标题 | 原因分析 | 解决方案 | 优先级 | 状态 | 提出人 | 历时 | 预计完成
 * Narrow cols get fixed width; 标题/原因/方案 share remaining space.
 */
.issues-table :deep(table) { table-layout: fixed; width: 100%; }
.issues-table :deep(:is(th, td):nth-child(1)) { width: 2.5%; }   /* select */
.issues-table :deep(:is(th, td):nth-child(2)) { width: 3.5%; }   /* ID */
/* 3: 标题 — 可拖拽调宽，默认 auto；宽度由 --title-col-w 注入 */
.issues-table :deep(:is(th, td):nth-child(3)) { width: var(--title-col-w, auto); }
.issues-table :deep(th:nth-child(3)) { position: relative; }
/* 4: 原因分析 — auto */
/* 5: 解决方案 — auto */
.issues-table :deep(:is(th, td):nth-child(6)) { width: 4.5%; }   /* 优先级 */
.issues-table :deep(:is(th, td):nth-child(7)) { width: 8%; }     /* 状态 */
.issues-table :deep(:is(th, td):nth-child(8)) { width: 6%; }     /* 提出人 */
.issues-table :deep(:is(th, td):nth-child(9)) { width: 7%; }    /* 历时 */
.issues-table :deep(:is(th, td):nth-child(10)) { width: 5%; }    /* 预计完成 */

/* 标题列「抓手」:右边界常驻一个双竖条握柄(始终可见、好发现),hover 时点亮主题紫
 * 并浮出柔光底,明确"可拖拽";表头/表体均不加分隔线,保持原有留白。 */
.title-header { display: flex; align-items: center; }
.col-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: 4px;
  cursor: col-resize;
  user-select: none;
  touch-action: none;
  transition: background-color 0.12s;
}
.col-resize-handle i {
  width: 1.5px;
  height: 12px;
  border-radius: 1px;
  background: #9ca3af; /* gray-400:常驻浅灰握柄 */
  transition: background-color 0.12s;
}
:root.dark .col-resize-handle i { background: #6b7280; } /* gray-500 */
/* 鼠标移到标题表头任意处即点亮抓手,提示可拖拽 */
.issues-table :deep(th:nth-child(3):hover .col-resize-handle) {
  background: rgba(139, 92, 246, 0.12); /* crystal-500 柔光底 */
}
.issues-table :deep(th:nth-child(3):hover .col-resize-handle i) {
  background: var(--color-crystal-500); /* 主题紫 */
}

/* 表格行按优先级着色:规则随站点设置动态生成,见 script 中 priorityRowCss + useHead */
</style>
