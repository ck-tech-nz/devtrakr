<template>
  <div v-if="loading" class="flex items-center justify-center py-20">
    <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
  </div>
  <div v-else-if="repo" class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">{{ repo.name }}</h1>
          <p class="text-sm text-gray-400 dark:text-gray-500 mt-0.5">{{ repo.full_name }}</p>
        </div>
        <UBadge :color="cloneStatusColor" variant="subtle">{{ cloneStatusLabel }}</UBadge>
      </div>
      <div class="flex items-center space-x-2">
        <UBadge :color="repo.status === '在线' ? 'success' : 'neutral'" variant="subtle">{{ repo.status }}</UBadge>
        <!-- Branch Switcher -->
        <USelect
          v-if="repo.clone_status === 'cloned'"
          v-model="selectedBranch"
          :items="branches"
          size="sm"
          placeholder="切换分支"
          @update:model-value="handleBranchSwitch"
        />
        <!-- Clone / Pull Button -->
        <UButton
          icon="i-heroicons-arrow-down-tray"
          variant="outline"
          color="neutral"
          size="sm"
          :loading="repo.clone_status === 'cloning'"
          @click="handleClone()"
        >
          {{ repo.clone_status === 'cloned' ? '拉取代码' : '克隆代码' }}
        </UButton>
        <UButton
          icon="i-heroicons-arrow-path"
          variant="outline"
          color="neutral"
          size="sm"
          :loading="syncing"
          @click="handleSync"
        >
          同步
        </UButton>
        <UButton
          icon="i-heroicons-information-circle"
          variant="ghost"
          color="neutral"
          size="sm"
          @click="showInfo = true"
        />
      </div>
    </div>

    <!-- Clone Error Alert -->
    <UAlert
      v-if="repo.clone_status === 'failed'"
      color="error"
      variant="subtle"
      icon="i-heroicons-exclamation-triangle"
      title="克隆失败"
      :description="repo.clone_error || '克隆仓库时发生错误，请重试'"
    />

    <!-- Dashboard Stats -->
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
      <DashboardStatCard
        label="Open Issues"
        :value="repo.open_issues_count ?? 0"
        icon="i-heroicons-exclamation-circle"
        icon-bg="bg-amber-50 dark:bg-amber-950"
        icon-color="text-amber-500"
      />
      <DashboardStatCard
        label="Closed Issues"
        :value="repo.closed_issues_count ?? 0"
        icon="i-heroicons-check-circle"
        icon-bg="bg-emerald-50 dark:bg-emerald-950"
        icon-color="text-emerald-500"
      />
      <div v-if="priorityStats.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
        <span class="text-sm text-gray-500 dark:text-gray-400">优先级分布</span>
        <div class="mt-2 flex flex-wrap gap-2">
          <UBadge
            v-for="p in priorityStats"
            :key="p.label"
            :color="p.label === 'P0' ? 'error' : p.label === 'P1' ? 'warning' : 'neutral'"
            variant="subtle"
            size="sm"
          >
            {{ p.label }}: {{ p.count }}
          </UBadge>
        </div>
      </div>
    </div>

    <!-- Tabs: Issues / Git Log -->
    <UTabs v-model="activeTab" :items="tabItems">
      <template #issues>
        <!-- View Toggle -->
        <div class="flex items-center justify-between mt-4 mb-4">
          <div class="flex items-center space-x-3">
            <div class="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
              <button
                class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
                :class="viewMode === 'kanban' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
                @click="viewMode = 'kanban'"
              >
                看板
              </button>
              <button
                class="px-3 py-1 text-xs font-medium rounded-md transition-colors"
                :class="viewMode === 'table' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
                @click="viewMode = 'table'"
              >
                列表
              </button>
            </div>
            <USelect
              v-if="viewMode === 'kanban'"
              v-model="kanbanGroup"
              :items="[{ label: '按状态', value: 'state' }, { label: '按标签', value: 'label' }]"
              value-key="value"
              size="xs"
            />
          </div>
          <span class="text-xs text-gray-400 dark:text-gray-500">共 {{ ghIssues.length }} 条</span>
        </div>

        <!-- Loading Issues -->
        <div v-if="issuesLoading" class="flex items-center justify-center py-10">
          <div class="text-sm text-gray-400 dark:text-gray-500">加载 Issues 中...</div>
        </div>

        <!-- Kanban View -->
        <SharedKanbanBoard
          v-else-if="viewMode === 'kanban'"
          :columns="kanbanColumns"
          :item-key="(item: any) => item.id"
          :draggable="false"
        >
          <template #card="{ item }">
            <NuxtLink :to="`/app/repos/${route.params.id}/issues/${item.id}`" class="block">
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-xs text-gray-400 dark:text-gray-500">#{{ item.github_id }}</span>
                <div class="flex items-center gap-1">
                  <UBadge
                    :color="item.state === 'open' ? 'warning' : 'success'"
                    variant="subtle"
                    size="xs"
                  >
                    {{ item.state === 'open' ? '开放' : '已关闭' }}
                  </UBadge>
                  <UBadge
                    v-if="extractPriority(item.labels)"
                    :color="extractPriority(item.labels)!.startsWith('P0') ? 'error' : extractPriority(item.labels)!.startsWith('P1') ? 'warning' : 'neutral'"
                    variant="subtle"
                    size="xs"
                  >
                    {{ extractPriority(item.labels) }}
                  </UBadge>
                </div>
              </div>
              <p class="text-sm text-gray-900 dark:text-gray-100 font-medium line-clamp-2">{{ item.title }}</p>
              <div v-if="item.assignees?.length" class="mt-2 flex items-center">
                <div class="w-5 h-5 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center">
                  <span class="text-crystal-600 dark:text-crystal-400 text-[10px] font-medium">{{ item.assignees[0].slice(0, 1).toUpperCase() }}</span>
                </div>
                <span class="ml-1.5 text-xs text-gray-400 dark:text-gray-500">{{ item.assignees[0] }}</span>
              </div>
            </NuxtLink>
          </template>
        </SharedKanbanBoard>

        <!-- Table View -->
        <div v-else-if="!issuesLoading" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
          <UTable
            :data="ghIssues"
            :columns="tableColumns"
            :ui="{ th: 'text-xs', td: 'text-sm' }"
          >
            <template #github_id-cell="{ row }">
              <span class="text-gray-500 dark:text-gray-400">#{{ row.original.github_id }}</span>
            </template>
            <template #title-cell="{ row }">
              <NuxtLink :to="`/app/repos/${route.params.id}/issues/${row.original.id}`" class="text-gray-900 dark:text-gray-100 hover:text-crystal-600 line-clamp-1">{{ row.original.title }}</NuxtLink>
            </template>
            <template #state-cell="{ row }">
              <UBadge :color="row.original.state === 'open' ? 'warning' : 'success'" variant="subtle" size="xs">
                {{ row.original.state === 'open' ? '开放' : '已关闭' }}
              </UBadge>
            </template>
            <template #labels-cell="{ row }">
              <div class="flex flex-wrap gap-1">
                <UBadge v-for="label in row.original.labels" :key="label" color="neutral" variant="subtle" size="xs">{{ label }}</UBadge>
              </div>
            </template>
            <template #assignees-cell="{ row }">
              {{ row.original.assignees?.join(', ') || '-' }}
            </template>
            <template #github_created_at-cell="{ row }">
              {{ row.original.github_created_at?.slice(0, 10) || '-' }}
            </template>
          </UTable>
        </div>
      </template>

      <template #pull-requests>
        <div class="mt-4">
          <div v-if="prsLoading" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">加载 PR 中...</div>
          </div>
          <div v-else-if="!pullRequests.length" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">暂无 PR,点击上方「同步」拉取</div>
          </div>
          <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <UTable :data="pullRequests" :columns="prColumns" :ui="{ th: 'text-xs', td: 'text-sm' }">
              <template #number-cell="{ row }">
                <a :href="row.original.html_url" target="_blank" class="font-mono text-xs text-primary-500 hover:underline">#{{ row.original.number }}</a>
              </template>
              <template #state-cell="{ row }">
                <UBadge :color="prStateColor(row.original.state)" variant="subtle" size="xs">{{ prStateLabel(row.original.state) }}</UBadge>
              </template>
              <template #linked_issues-cell="{ row }">
                <div class="flex flex-wrap gap-1">
                  <NuxtLink
                    v-for="li in row.original.linked_issues"
                    :key="li.id"
                    :to="`/app/issues/${li.id}`"
                    class="text-xs text-primary-500 hover:underline"
                  >{{ li.ref }}</NuxtLink>
                  <span v-if="!row.original.linked_issues.length" class="text-xs text-gray-400">-</span>
                </div>
              </template>
              <template #github_updated_at-cell="{ row }">
                {{ row.original.github_updated_at?.slice(0, 16)?.replace('T', ' ') || '-' }}
              </template>
            </UTable>
          </div>
        </div>
      </template>

      <template #git-log>
        <div class="mt-4">
          <!-- Loading Git Log -->
          <div v-if="gitLogLoading" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">加载提交记录中...</div>
          </div>
          <!-- Not Cloned Notice -->
          <div v-else-if="repo.clone_status !== 'cloned'" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">请先克隆代码后查看提交记录</div>
          </div>
          <!-- Git Log Table -->
          <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
            <UTable
              :data="gitLog"
              :columns="gitLogColumns"
              :ui="{ th: 'text-xs', td: 'text-sm' }"
            >
              <template #hash-cell="{ row }">
                <span class="font-mono text-xs text-gray-500 dark:text-gray-400">{{ row.original.hash?.slice(0, 7) }}</span>
              </template>
              <template #date-cell="{ row }">
                {{ row.original.date?.slice(0, 16)?.replace('T', ' ') || '-' }}
              </template>
              <template #message-cell="{ row }">
                <span class="line-clamp-1">{{ row.original.message }}</span>
              </template>
            </UTable>
          </div>
        </div>
      </template>

      <template #insights>
        <div class="mt-4">
          <!-- Loading -->
          <div v-if="insightsLoading" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">加载开发者洞察中...</div>
          </div>
          <!-- Not Cloned -->
          <div v-else-if="repo.clone_status !== 'cloned'" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">请先克隆代码后查看开发者洞察</div>
          </div>
          <!-- Individual Detail View -->
          <div v-else-if="selectedDeveloper && developerDetail" class="space-y-4">
            <div class="flex items-center justify-between">
              <button class="text-sm text-primary hover:underline" @click="backToTeam">← 返回团队总览</button>
              <USelect v-model="insightsDays" :items="daysOptions" value-key="value" size="xs" />
            </div>
            <!-- Header -->
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                <span class="text-primary font-semibold">{{ developerDetail.author_name?.slice(0, 1)?.toUpperCase() }}</span>
              </div>
              <div>
                <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ developerDetail.author_name }}</h3>
                <p class="text-xs text-gray-400 dark:text-gray-500">{{ developerDetail.author_email }}<span v-if="developerDetail.user_name"> · {{ developerDetail.user_name }}</span></p>
              </div>
            </div>
            <!-- Radar Chart -->
            <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4">
              <ChartsRadarChart
                :indicators="[
                  { name: '贡献量', max: 100 },
                  { name: '效率', max: 100 },
                  { name: '能力', max: 100 },
                  { name: '质量', max: 100 },
                ]"
                :values="[
                  developerDetail.scores.contribution,
                  developerDetail.scores.efficiency,
                  developerDetail.scores.capability,
                  developerDetail.scores.quality,
                ]"
                :height="280"
              />
            </div>
            <!-- Detail Cards -->
            <div class="grid grid-cols-2 gap-3">
              <div class="bg-emerald-50 dark:bg-emerald-950/30 rounded-xl p-4">
                <p class="text-xs font-semibold text-emerald-600 dark:text-emerald-400 mb-2">贡献量</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">提交数: {{ developerDetail.details.commit_count }}</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">代码行数: +{{ developerDetail.details.additions }} / -{{ developerDetail.details.deletions }}</p>
              </div>
              <div class="bg-blue-50 dark:bg-blue-950/30 rounded-xl p-4">
                <p class="text-xs font-semibold text-blue-600 dark:text-blue-400 mb-2">效率</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">频率: {{ developerDetail.details.commit_frequency }}/周</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">活跃天数: {{ developerDetail.details.active_days_ratio }}%</p>
              </div>
              <div class="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-4">
                <p class="text-xs font-semibold text-amber-600 dark:text-amber-400 mb-2">能力</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">涉及目录: {{ developerDetail.details.directory_count }} 个</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">
                  类型:
                  <span v-for="(count, type) in developerDetail.details.commit_types" :key="type" class="mr-1">
                    {{ type }} {{ count }}
                  </span>
                </p>
              </div>
              <div class="bg-purple-50 dark:bg-purple-950/30 rounded-xl p-4">
                <p class="text-xs font-semibold text-purple-600 dark:text-purple-400 mb-2">质量</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">Fix 占比: {{ developerDetail.details.fix_ratio }}%</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">规范度: {{ developerDetail.details.conventional_ratio }}%</p>
              </div>
            </div>
            <!-- AI Placeholder -->
            <div class="border border-dashed border-gray-200 dark:border-gray-700 rounded-xl p-4">
              <p class="text-xs font-semibold text-gray-400 dark:text-gray-500">AI 洞察 (即将推出)</p>
              <p class="text-xs text-gray-300 dark:text-gray-600 mt-1 italic">基于提交历史和 Issue 数据的综合分析...</p>
            </div>
          </div>
          <!-- Loading Detail -->
          <div v-else-if="selectedDeveloper && developerDetailLoading" class="flex items-center justify-center py-10">
            <div class="text-sm text-gray-400 dark:text-gray-500">加载开发者详情中...</div>
          </div>
          <!-- Team Overview -->
          <div v-else-if="insightsData" class="space-y-4">
            <!-- Time filter -->
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-gray-700 dark:text-gray-300">开发者洞察</span>
              <USelect v-model="insightsDays" :items="daysOptions" value-key="value" size="xs" />
            </div>
            <!-- Unlinked authors alert -->
            <UAlert
              v-if="insightsData.unlinked_count > 0"
              color="warning"
              variant="subtle"
              icon="i-heroicons-exclamation-triangle"
              :title="`${insightsData.unlinked_count} 位作者未关联用户`"
              :actions="[{ label: '去关联', onClick: () => { showLinkModal = true; fetchUsers() } }]"
            />
            <!-- Developer Cards -->
            <div class="space-y-3">
              <div
                v-for="dev in insightsData.developers"
                :key="dev.author_email"
                class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 cursor-pointer hover:border-primary transition-colors"
                @click="selectDeveloper(dev)"
              >
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center gap-2">
                    <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <span class="text-primary text-sm font-semibold">{{ dev.author_name?.slice(0, 1)?.toUpperCase() }}</span>
                    </div>
                    <div>
                      <span class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ dev.author_name }}</span>
                      <span class="text-xs text-gray-400 dark:text-gray-500 ml-2">{{ dev.stats.commit_count }} commits</span>
                      <span v-if="dev.user_name" class="text-xs text-gray-400 dark:text-gray-500 ml-1">· {{ dev.user_name }}</span>
                    </div>
                  </div>
                  <span class="text-xs text-primary">查看详情 →</span>
                </div>
                <!-- Score bars -->
                <div class="grid grid-cols-4 gap-3">
                  <div v-for="(dim, key) in { contribution: '贡献量', efficiency: '效率', capability: '能力', quality: '质量' }" :key="key">
                    <div class="flex justify-between text-[11px] mb-1">
                      <span class="text-gray-500 dark:text-gray-400">{{ dim }}</span>
                      <span class="font-semibold" :class="scoreColor(key as string)">{{ dev.scores[key] }}</span>
                    </div>
                    <div class="h-1 bg-gray-100 dark:bg-gray-800 rounded-full">
                      <div class="h-full rounded-full transition-all" :class="scoreBarColor(key as string)" :style="{ width: dev.scores[key] + '%' }" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Link Authors Slideover -->
          <USlideover v-model:open="showLinkModal" title="关联 Git 作者" side="right">
            <template #content>
              <div class="p-6 space-y-4">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">关联 Git 作者到系统用户</h3>
                <div v-for="author in insightsData?.unlinked_authors" :key="author.id" class="flex items-center gap-3 py-2 border-b border-gray-100 dark:border-gray-800">
                  <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ author.author_name }}</p>
                    <p class="text-xs text-gray-400 dark:text-gray-500 truncate">{{ author.author_email }}</p>
                  </div>
                  <USelect
                    :items="allUsers.map((u: any) => ({ label: u.name || u.username, value: u.id }))"
                    value-key="value"
                    placeholder="选择用户"
                    size="sm"
                    class="w-40"
                    @update:model-value="(val: any) => linkAuthor(author.id, val)"
                  />
                </div>
              </div>
            </template>
          </USlideover>
        </div>
      </template>
    </UTabs>

    <!-- Info Slideover -->
    <USlideover v-model:open="showInfo" title="仓库信息" side="right">
      <template #content>
        <div class="p-6 space-y-4">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">仓库信息</h3>
          <div class="space-y-3">
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">GitHub URL</p>
              <a :href="repo.url" target="_blank" class="text-sm text-crystal-500 hover:text-crystal-700 break-all">{{ repo.url }}</a>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">默认分支</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.default_branch }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">当前分支</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.current_branch || '-' }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">状态</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.status }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">绑定时间</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.connected_at?.slice(0, 10) }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">最近同步</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.last_synced_at?.slice(0, 16)?.replace('T', ' ') || '从未同步' }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 dark:text-gray-500">克隆时间</p>
              <p class="text-sm text-gray-900 dark:text-gray-100">{{ repo.cloned_at?.slice(0, 16)?.replace('T', ' ') || '未克隆' }}</p>
            </div>
          </div>
        </div>
      </template>
    </USlideover>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const route = useRoute()
const { api } = useApi()
const toast = useToast()

const loading = ref(true)
const repo = ref<any>(null)
const ghIssues = ref<any[]>([])
const issuesLoading = ref(false)
const syncing = ref(false)
const showInfo = ref(false)
const viewMode = ref<'kanban' | 'table'>('kanban')
const kanbanGroup = ref('state')
const activeTab = ref('issues')

// Git log state
const gitLog = ref<any[]>([])
const gitLogLoading = ref(false)

// Pull Requests state
const pullRequests = ref<PullRequestRow[]>([])
const prsLoading = ref(false)

// Developer insights state
const insightsData = ref<any>(null)
const insightsLoading = ref(false)
const selectedDeveloper = ref<any>(null)
const developerDetail = ref<any>(null)
const developerDetailLoading = ref(false)
const insightsDays = ref('90')
const showLinkModal = ref(false)
const allUsers = ref<any[]>([])

// Branches state
const branches = ref<string[]>([])
const selectedBranch = ref<string>('')

// Poll timer ref
let pollTimer: ReturnType<typeof setTimeout> | null = null

const tabItems = [
  { label: 'Issues', slot: 'issues', value: 'issues' },
  { label: 'Pull Requests', slot: 'pull-requests', value: 'pull-requests' },
  { label: '提交记录', slot: 'git-log', value: 'git-log' },
  { label: '开发者洞察', slot: 'insights', value: 'insights' },
]

const tableColumns = [
  { accessorKey: 'github_id', header: '#' },
  { accessorKey: 'title', header: '标题' },
  { accessorKey: 'state', header: '状态' },
  { accessorKey: 'labels', header: '标签' },
  { accessorKey: 'assignees', header: '负责人' },
  { accessorKey: 'github_created_at', header: '创建时间' },
]

const gitLogColumns = [
  { accessorKey: 'hash', header: '提交哈希' },
  { accessorKey: 'author', header: '作者' },
  { accessorKey: 'date', header: '日期' },
  { accessorKey: 'message', header: '提交信息' },
]

const prColumns = [
  { accessorKey: 'number', header: '#' },
  { accessorKey: 'title', header: '标题' },
  { accessorKey: 'state', header: '状态' },
  { accessorKey: 'linked_issues', header: '关联 Issue' },
  { accessorKey: 'github_updated_at', header: '更新时间' },
]

const cloneStatusColor = computed(() => {
  switch (repo.value?.clone_status) {
    case 'cloned': return 'success'
    case 'cloning': return 'warning'
    case 'failed': return 'error'
    default: return 'neutral'
  }
})

const cloneStatusLabel = computed(() => {
  switch (repo.value?.clone_status) {
    case 'cloned': return '已克隆'
    case 'cloning': return '克隆中'
    case 'failed': return '失败'
    default: return '未克隆'
  }
})

function extractPriority(labels: string[]): string | null {
  if (!labels?.length) return null
  const match = labels.find(l => /^P[0-3]$/i.test(l) || /priority/i.test(l))
  return match || null
}

const priorityStats = computed(() => {
  const counts: Record<string, number> = {}
  for (const issue of ghIssues.value) {
    const p = extractPriority(issue.labels)
    if (p) counts[p] = (counts[p] || 0) + 1
  }
  return Object.entries(counts)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => a.label.localeCompare(b.label))
})

const kanbanColumns = computed(() => {
  if (kanbanGroup.value === 'state') {
    return [
      { key: 'open', label: '开放', items: ghIssues.value.filter(i => i.state === 'open') },
      { key: 'closed', label: '已关闭', items: ghIssues.value.filter(i => i.state === 'closed') },
    ]
  }
  const labelMap: Record<string, any[]> = {}
  for (const issue of ghIssues.value) {
    if (!issue.labels?.length) {
      const key = '无标签'
      if (!labelMap[key]) labelMap[key] = []
      labelMap[key].push(issue)
    } else {
      for (const label of issue.labels) {
        if (!labelMap[label]) labelMap[label] = []
        labelMap[label].push(issue)
      }
    }
  }
  return Object.entries(labelMap).map(([key, items]) => ({
    key,
    label: key,
    items,
  }))
})

async function fetchIssues() {
  issuesLoading.value = true
  try {
    ghIssues.value = await api<any[]>(`/api/repos/github-issues/?repo=${route.params.id}`)
  } catch (e) {
    console.error('Failed to load GitHub issues:', e)
  } finally {
    issuesLoading.value = false
  }
}

async function fetchBranches() {
  try {
    const data = await api<string[]>(`/api/repos/${route.params.id}/branches/`)
    branches.value = data
    if (repo.value?.current_branch) {
      selectedBranch.value = repo.value.current_branch
    }
  } catch (e) {
    console.error('Failed to load branches:', e)
  }
}

async function fetchPullRequests() {
  prsLoading.value = true
  try {
    pullRequests.value = await api<PullRequestRow[]>(`/api/repos/${route.params.id}/pull-requests/`)
  } catch (e) {
    console.error('Failed to load pull requests:', e)
  } finally {
    prsLoading.value = false
  }
}

async function fetchGitLog() {
  if (repo.value?.clone_status !== 'cloned') return
  gitLogLoading.value = true
  try {
    gitLog.value = await api<any[]>(`/api/repos/${route.params.id}/git-log/?limit=50`)
  } catch (e) {
    console.error('Failed to load git log:', e)
  } finally {
    gitLogLoading.value = false
  }
}

const daysOptions = [
  { label: '30天', value: '30' },
  { label: '90天', value: '90' },
  { label: '全部', value: 'all' },
]

async function fetchInsights() {
  if (repo.value?.clone_status !== 'cloned') return
  insightsLoading.value = true
  try {
    insightsData.value = await api<any>(
      `/api/repos/${route.params.id}/developer-insights/?days=${insightsDays.value}`
    )
  } catch (e) {
    console.error('Failed to load insights:', e)
  } finally {
    insightsLoading.value = false
  }
}

async function fetchDeveloperDetail(aliasId: number) {
  developerDetailLoading.value = true
  try {
    developerDetail.value = await api<any>(
      `/api/repos/${route.params.id}/developer-insights/${aliasId}/?days=${insightsDays.value}`
    )
  } catch (e) {
    console.error('Failed to load developer detail:', e)
  } finally {
    developerDetailLoading.value = false
  }
}

function selectDeveloper(dev: any) {
  selectedDeveloper.value = dev
  fetchDeveloperDetail(dev.alias_id)
}

function backToTeam() {
  selectedDeveloper.value = null
  developerDetail.value = null
}

async function fetchUsers() {
  try {
    const data = await api<any>('/api/users/choices/')
    allUsers.value = data
  } catch (e) {
    console.error('Failed to load users:', e)
  }
}

async function linkAuthor(aliasId: number, userId: number | null) {
  try {
    await api(`/api/repos/${route.params.id}/git-author-aliases/${aliasId}/`, {
      method: 'PATCH',
      body: { user: userId },
    })
    toast.add({ title: '关联成功', color: 'success' })
    await fetchInsights()
  } catch (e) {
    toast.add({ title: '关联失败', color: 'error' })
  }
}

function scoreColor(key: string): string {
  const colors: Record<string, string> = {
    contribution: 'text-emerald-600 dark:text-emerald-400',
    efficiency: 'text-blue-600 dark:text-blue-400',
    capability: 'text-amber-600 dark:text-amber-400',
    quality: 'text-purple-600 dark:text-purple-400',
  }
  return colors[key] || ''
}

function scoreBarColor(key: string): string {
  const colors: Record<string, string> = {
    contribution: 'bg-emerald-500',
    efficiency: 'bg-blue-500',
    capability: 'bg-amber-500',
    quality: 'bg-purple-500',
  }
  return colors[key] || ''
}

async function handleSync() {
  syncing.value = true
  try {
    const data = await api<any>(`/api/repos/${route.params.id}/sync/`, { method: 'POST' })
    repo.value = data
    await fetchIssues()
    await fetchPullRequests()
    toast.add({ title: `已同步 ${ghIssues.value.length} 条 Issue`, color: 'success' })
  } catch (e: any) {
    console.error('Sync failed:', e)
    const detail = e?.data?.detail || e?.response?._data?.detail || '同步失败，请重试'
    toast.add({ title: detail, color: 'error' })
  } finally {
    syncing.value = false
  }
}

async function handleClone(branch?: string) {
  try {
    const body: Record<string, string> = {}
    if (branch) body.branch = branch
    await api(`/api/repos/${route.params.id}/clone/`, { method: 'POST', body })
    // Update local status to cloning and start polling
    repo.value = { ...repo.value, clone_status: 'cloning' }
    startPolling()
    toast.add({ title: '已发起拉取代码任务', color: 'success' })
  } catch (e: any) {
    console.error('Clone failed:', e)
    const detail = e?.data?.detail || e?.response?._data?.detail || '操作失败，请重试'
    toast.add({ title: detail, color: 'error' })
  }
}

async function handleBranchSwitch(branch: string) {
  if (!branch) return
  await handleClone(branch)
}

function startPolling() {
  stopPolling()
  pollTimer = setTimeout(pollRepoStatus, 3000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

async function pollRepoStatus() {
  try {
    const data = await api<any>(`/api/repos/${route.params.id}/`)
    repo.value = data
    if (data.clone_status === 'cloning') {
      // Still cloning — schedule next poll
      pollTimer = setTimeout(pollRepoStatus, 3000)
    } else {
      pollTimer = null
      if (data.clone_status === 'cloned') {
        await fetchBranches()
        await fetchGitLog()
      }
    }
  } catch (e) {
    console.error('Poll failed:', e)
    pollTimer = null
  }
}

// Fetch git log when switching to git-log tab; fetch insights when switching to insights tab
watch(activeTab, (val) => {
  if (val === 'pull-requests' && !pullRequests.value.length) {
    fetchPullRequests()
  }
  if (val === 'git-log' && repo.value?.clone_status === 'cloned' && !gitLog.value.length) {
    fetchGitLog()
  }
  if (val === 'insights' && repo.value?.clone_status === 'cloned' && !insightsData.value) {
    fetchInsights()
  }
})

watch(insightsDays, () => {
  if (activeTab.value === 'insights') {
    fetchInsights()
    if (selectedDeveloper.value) {
      fetchDeveloperDetail(selectedDeveloper.value.alias_id)
    }
  }
})

onMounted(async () => {
  try {
    const [repoData] = await Promise.all([
      api<any>(`/api/repos/${route.params.id}/`),
    ])
    repo.value = repoData
    await fetchIssues()
    if (repoData.clone_status === 'cloned') {
      await fetchBranches()
    } else if (repoData.clone_status === 'cloning') {
      startPolling()
    }
  } catch (e) {
    console.error('Failed to load repo:', e)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>
