<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">KPI 评分规则</h1>
      <UButton
        size="sm"
        icon="i-heroicons-check"
        :loading="saving"
        @click="handleSave"
      >
        保存
      </UButton>
    </div>

    <div v-if="loading" class="text-center py-20 text-sm text-gray-400">加载中...</div>

    <template v-else-if="config">
      <!-- 综合分维度权重 -->
      <ScoringCard title="综合分维度权重" description="5 个维度在综合分中的权重，总和应为 1.0">
        <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <ScoringField
            v-for="(val, key) in config.dimension_weights"
            :key="key"
            :label="dimLabel(key as string)"
            :model-value="val as number"
            @update:model-value="config.dimension_weights[key] = $event"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </div>
        <WeightSum :weights="config.dimension_weights" />
      </ScoringCard>

      <!-- 效率 -->
      <ScoringCard title="效率评分公式" description="效率维度各子指标权重">
        <div class="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <ScoringField
            v-for="(val, key) in config.efficiency_formula"
            :key="key"
            :label="subLabel('efficiency', key as string)"
            :model-value="val as number"
            @update:model-value="config.efficiency_formula[key] = $event"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </div>
        <WeightSum :weights="config.efficiency_formula" />
      </ScoringCard>

      <!-- 产出 -->
      <ScoringCard title="产出评分公式" description="产出维度各子指标权重">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <ScoringField
            v-for="(val, key) in config.output_formula"
            :key="key"
            :label="subLabel('output', key as string)"
            :model-value="val as number"
            @update:model-value="config.output_formula[key] = $event"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </div>
        <WeightSum :weights="config.output_formula" />
      </ScoringCard>

      <!-- 质量 -->
      <ScoringCard title="质量评分公式" description="质量维度各子指标权重">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <ScoringField
            v-for="(val, key) in config.quality_formula"
            :key="key"
            :label="subLabel('quality', key as string)"
            :model-value="val as number"
            @update:model-value="config.quality_formula[key] = $event"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </div>
        <WeightSum :weights="config.quality_formula" />
      </ScoringCard>

      <!-- 能力 -->
      <ScoringCard title="能力评分公式" description="能力维度各子指标权重">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <ScoringField
            v-for="(val, key) in config.capability_formula"
            :key="key"
            :label="subLabel('capability', key as string)"
            :model-value="val as number"
            @update:model-value="config.capability_formula[key] = $event"
            :step="0.05"
            :min="0"
            :max="1"
          />
        </div>
        <WeightSum :weights="config.capability_formula" />
      </ScoringCard>

      <!-- 饱和天花板值 -->
      <ScoringCard title="饱和天花板值" description="各指标达到满分 100 的阈值">
        <div class="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <ScoringField
            v-for="(val, key) in config.ceilings"
            :key="key"
            :label="ceilingLabel(key as string)"
            :model-value="val as number"
            @update:model-value="config.ceilings[key] = $event"
            :step="1"
            :min="1"
            :max="1000"
          />
        </div>
      </ScoringCard>

      <!-- 工单计件 - 数量梯度 -->
      <ScoringCard
        title="工单计件 · 数量梯度"
        description="小型工单 (< 中型工时阈值) 按累计完成数量分段定价。max_count 留空 = 上不封顶"
      >
        <div class="space-y-2">
          <div class="grid grid-cols-[1fr_1fr_auto] gap-3 items-end text-xs text-gray-500 dark:text-gray-400">
            <span>累计前 N 个 (空 = ∞)</span>
            <span>单价 (¥)</span>
            <span></span>
          </div>
          <div
            v-for="(tier, idx) in pieceRate.count_tiers"
            :key="idx"
            class="grid grid-cols-[1fr_1fr_auto] gap-3 items-center"
          >
            <UInput
              type="number"
              size="sm"
              :model-value="tier.max_count ?? ''"
              placeholder="不限"
              @update:model-value="tier.max_count = ($event === '' || $event == null) ? null : Number($event)"
              :min="1"
            />
            <UInput
              type="number"
              size="sm"
              :model-value="tier.price"
              @update:model-value="tier.price = Number($event)"
              :min="0"
              :step="10"
            />
            <UButton
              size="xs"
              variant="ghost"
              color="error"
              icon="i-heroicons-trash"
              :disabled="pieceRate.count_tiers.length <= 1"
              @click="pieceRate.count_tiers.splice(idx, 1)"
            />
          </div>
          <UButton
            size="xs"
            variant="outline"
            color="neutral"
            icon="i-heroicons-plus"
            @click="pieceRate.count_tiers.push({ max_count: null, price: 100 })"
          >
            添加梯度
          </UButton>
        </div>
      </ScoringCard>

      <!-- 工单计件 - 工时分级 -->
      <ScoringCard
        title="工单计件 · 工时分级"
        description="单工单实际工时落入区间时改用固定价 (覆盖数量梯度)。max_hours 留空 = 上不封顶"
      >
        <div class="space-y-2">
          <div class="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-3 items-end text-xs text-gray-500 dark:text-gray-400">
            <span>标签</span>
            <span>最小工时</span>
            <span>最大工时 (空=∞)</span>
            <span>单价 (¥)</span>
            <span></span>
          </div>
          <div
            v-for="(br, idx) in pieceRate.hour_brackets"
            :key="idx"
            class="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-3 items-center"
          >
            <UInput
              size="sm"
              :model-value="br.label ?? ''"
              @update:model-value="br.label = String($event)"
              placeholder="中型"
            />
            <UInput
              type="number"
              size="sm"
              :model-value="br.min_hours"
              @update:model-value="br.min_hours = Number($event)"
              :min="0"
              :step="0.5"
            />
            <UInput
              type="number"
              size="sm"
              :model-value="br.max_hours ?? ''"
              placeholder="不限"
              @update:model-value="br.max_hours = ($event === '' || $event == null) ? null : Number($event)"
              :min="0"
              :step="0.5"
            />
            <UInput
              type="number"
              size="sm"
              :model-value="br.price"
              @update:model-value="br.price = Number($event)"
              :min="0"
              :step="50"
            />
            <UButton
              size="xs"
              variant="ghost"
              color="error"
              icon="i-heroicons-trash"
              @click="pieceRate.hour_brackets.splice(idx, 1)"
            />
          </div>
          <UButton
            size="xs"
            variant="outline"
            color="neutral"
            icon="i-heroicons-plus"
            @click="pieceRate.hour_brackets.push({ label: '', min_hours: 0, max_hours: null, price: 250 })"
          >
            添加分级
          </UButton>
        </div>
      </ScoringCard>

      <!-- 段位阈值 + 保护期 -->
      <ScoringCard
        title="段位阈值 & 保护期"
        description="综合分 ≥ 阈值 即获得对应段位。保护期 = 工单完成后多少天内复发记为重修"
      >
        <div class="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <ScoringField
            v-for="key in TIER_ORDER"
            :key="key"
            :label="tierLabel(key) + ' (≥)'"
            :model-value="pieceRate.tier_thresholds[key] ?? 0"
            @update:model-value="pieceRate.tier_thresholds[key] = $event"
            :step="1"
            :min="0"
            :max="100"
          />
        </div>
        <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 grid grid-cols-2 lg:grid-cols-3 gap-4">
          <ScoringField
            label="保护期 (天)"
            :model-value="pieceRate.protection_days"
            @update:model-value="pieceRate.protection_days = $event"
            :step="1"
            :min="1"
            :max="90"
          />
        </div>
      </ScoringCard>

      <!-- 算法说明 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">算法说明</h3>
        <div class="prose prose-sm dark:prose-invert max-w-none text-gray-600 dark:text-gray-400 space-y-5">

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">综合分计算</h4>
            <p>综合分 = 效率 × W<sub>效率</sub> + 产出 × W<sub>产出</sub> + 质量 × W<sub>质量</sub> + 能力 × W<sub>能力</sub> + 成长 × W<sub>成长</sub></p>
            <p>各维度权重之和应等于 1.0，每个维度评分范围 0-100。</p>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">效率维度</h4>
            <ul class="list-disc pl-5 space-y-1">
              <li><b>日均解决</b> — 期间平均每天解决的问题数，达到天花板值即满分</li>
              <li><b>解决速度</b> — 平均解决耗时的反向映射：0 小时 = 100 分，达到天花板值（默认 168h）= 0 分</li>
              <li><b>P0/P1 速度</b> — P0（权重 2）和 P1（权重 1）的加权平均解决时间，同样反向映射</li>
            </ul>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">产出维度</h4>
            <ul class="list-disc pl-5 space-y-1">
              <li><b>加权价值</b> — 按优先级加权的已解决问题总价值（P0=4, P1=3, P2=2, P3=1）</li>
              <li><b>解决数量</b> — 期间已解决问题总数</li>
              <li><b>提交量</b> — 期间 Git commit 总数</li>
              <li><b>仓库广度</b> — 有提交的仓库数量</li>
            </ul>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">质量维度</h4>
            <ul class="list-disc pl-5 space-y-1">
              <li><b>反向 Bug 率</b> — (1 - 自引 Bug 率) × 100，Bug 率越低分数越高</li>
              <li><b>反向 Churn 率</b> — (1 - 代码 Churn 率) × 100，Churn 率越低越好</li>
              <li><b>提交大小</b> — 平均 commit 大小在 50-150 行为满分，偏离越大扣分越多（高斯衰减）</li>
              <li><b>规范提交率</b> — 符合 Conventional Commits 规范的提交占比</li>
            </ul>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">能力维度</h4>
            <ul class="list-disc pl-5 space-y-1">
              <li><b>文件类型广度</b> — 涉及的不同文件扩展名种类数</li>
              <li><b>仓库覆盖</b> — 有提交的仓库数量</li>
              <li><b>P0 处理比</b> — 已解决的 P0 问题占全部已解决问题的比例</li>
              <li><b>协助参与</b> — 以协助者身份参与的问题数</li>
            </ul>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">成长维度</h4>
            <p>与上一周期四个维度（效率、产出、质量、能力）的均分差值映射到 0-100：差值为 0 → 50 分，+50 → 100 分，-50 → 0 分。首次无历史数据时固定为 50。</p>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">饱和天花板值</h4>
            <p>各子指标使用线性饱和映射：<code>分数 = min(实际值 / 天花板值 × 100, 100)</code>。例如"日均解决"天花板为 3，当日均解决 1.5 个时得分 50，达到 3 个时得分 100。调高天花板使满分更难获得，调低则更容易。</p>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">工单计件 (Code Arena)</h4>
            <ul class="list-disc pl-5 space-y-1">
              <li><b>工时分级优先</b> — 工单的<b>预计工时</b> (<code>estimated_hours</code>，默认 4h，管理员可修改) 若落在工时分级区间，则采用固定价。</li>
              <li><b>数量梯度</b> — 预计工时落入"短工单"区间 (即未匹配任何分级) 时，按完成顺序累积，落在哪个梯度就用哪个单价。</li>
              <li><b>段位</b> — 综合分映射到段位：≥ 对应阈值即为该段位。最低阈值始终为青铜。</li>
              <li><b>保护期</b> — 工单标记完成后 N 天内若状态回退到未完成，记为一次重修 (rework_count)，作为未来"关联惩罚"机制的数据基础。</li>
              <li><b>拖延度</b> — <code>actual_hours / estimated_hours</code> 的均值。&gt; 1 表示超出预计工时，仅用于考核工作拖延程度，不参与工单规模分级。</li>
            </ul>
          </div>

        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const { api } = useApi()
const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const config = ref<any>(null)

const DIM_LABELS: Record<string, string> = {
  efficiency: '效率',
  output: '产出',
  quality: '质量',
  capability: '能力',
  growth: '成长',
}

const SUB_LABELS: Record<string, Record<string, string>> = {
  efficiency: {
    daily_resolved: '日均解决',
    speed: '解决速度',
    p0p1_speed: 'P0/P1 速度',
  },
  output: {
    weighted_issue_value: '加权价值',
    resolved_count: '解决数量',
    commit_volume: '提交量',
    repo_breadth: '仓库广度',
  },
  quality: {
    inv_bug_rate: '反向 Bug 率',
    inv_churn_rate: '反向 Churn 率',
    commit_size: '提交大小',
    conventional_ratio: '规范提交率',
  },
  capability: {
    file_type_breadth: '文件类型广度',
    repo_coverage: '仓库覆盖',
    p0_handling_ratio: 'P0 处理比',
    helper_participation: '协助参与',
  },
}

const CEILING_LABELS: Record<string, string> = {
  daily_resolved: '日均解决 (个)',
  avg_hours: '平均解决时间 (小时)',
  p0p1_hours: 'P0/P1 解决时间 (小时)',
  weighted_value: '加权价值上限',
  resolved_count: '期间解决数 (个)',
  commit_volume: '提交量 (个)',
  repo_breadth: '仓库覆盖 (个)',
  file_type: '文件类型 (种)',
  helper_count: '协助数量 (个)',
}

const TIER_ORDER = ['bronze', 'silver', 'gold', 'platinum', 'diamond', 'master'] as const
const TIER_LABELS: Record<string, string> = {
  bronze: '青铜',
  silver: '白银',
  gold: '黄金',
  platinum: '铂金',
  diamond: '钻石',
  master: '王者',
}

function dimLabel(key: string) { return DIM_LABELS[key] || key }
function subLabel(dim: string, key: string) { return SUB_LABELS[dim]?.[key] || key }
function ceilingLabel(key: string) { return CEILING_LABELS[key] || key }
function tierLabel(key: string) { return TIER_LABELS[key] || key }

interface PieceRateConfig {
  count_tiers: Array<{ max_count: number | null; price: number }>
  hour_brackets: Array<{ label?: string; min_hours: number; max_hours: number | null; price: number }>
  tier_thresholds: Record<string, number>
  protection_days: number
}

const pieceRate = computed<PieceRateConfig>(() => {
  if (!config.value) {
    return {
      count_tiers: [],
      hour_brackets: [],
      tier_thresholds: {},
      protection_days: 7,
    }
  }
  // 缺省时填充骨架，保证模板里可直接索引
  if (!config.value.piece_rate_config) {
    config.value.piece_rate_config = {
      count_tiers: [{ max_count: 20, price: 100 }, { max_count: null, price: 160 }],
      hour_brackets: [
        { label: '中型', min_hours: 4, max_hours: 16, price: 250 },
        { label: '大型', min_hours: 16, max_hours: null, price: 600 },
      ],
      tier_thresholds: { bronze: 0, silver: 50, gold: 65, platinum: 75, diamond: 85, master: 95 },
      protection_days: 7,
    }
  }
  return config.value.piece_rate_config
})

async function fetchConfig() {
  loading.value = true
  try {
    config.value = await api('/api/kpi/scoring-config/')
  } catch { /* empty */ } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const { updated_at, ...payload } = config.value
    config.value = await api('/api/kpi/scoring-config/', { method: 'PUT', body: payload })
    toast.add({ title: '评分规则已保存', color: 'success' })
  } catch (e: any) {
    toast.add({ title: '保存失败', description: e?.data?.detail || '请稍后重试', color: 'error' })
  } finally {
    saving.value = false
  }
}

onMounted(fetchConfig)
</script>
