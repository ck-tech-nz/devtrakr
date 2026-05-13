<template>
  <div class="space-y-6">
    <!-- 返回按钮 -->
    <NuxtLink to="/app/kpi" class="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
      <UIcon name="i-heroicons-arrow-left" class="w-4 h-4" />
      返回团队 KPI
    </NuxtLink>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="text-sm text-gray-400 dark:text-gray-500">加载中...</div>
    </div>

    <template v-else-if="summary">
      <!-- 用户信息卡片 -->
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-6">
        <div class="flex items-center gap-4 flex-wrap">
          <img
            v-if="summary.avatar"
            :src="resolveAvatarUrl(summary.avatar)"
            class="w-16 h-16 rounded-full"
          />
          <div
            v-else
            class="w-16 h-16 rounded-full bg-crystal-100 dark:bg-crystal-900 flex items-center justify-center text-xl font-semibold text-crystal-600 dark:text-crystal-400"
          >
            {{ (summary.user_name || '?').slice(0, 1) }}
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-baseline gap-3 flex-wrap">
              <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{{ summary.user_name }}</h1>
              <span class="text-sm text-gray-500 dark:text-gray-400">{{ period.label.value }}</span>
            </div>
            <div class="flex gap-1.5 mt-1.5 flex-wrap items-center">
              <UBadge
                v-for="g in (summary.groups || [])"
                :key="g"
                color="neutral"
                variant="subtle"
                size="xs"
              >
                {{ g }}
              </UBadge>
              <UBadge
                v-if="summary.scores?.tier?.label"
                :class="tierBadgeClass(summary.scores.tier.key)"
                variant="subtle"
                size="xs"
              >
                <UIcon name="i-heroicons-trophy" class="w-3 h-3 mr-0.5" />
                {{ summary.scores.tier.label }}
              </UBadge>
            </div>
          </div>
          <div class="text-right">
            <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">综合评分</div>
            <div class="text-4xl font-bold text-crystal-600 dark:text-crystal-400">
              {{ summary.scores?.overall != null ? Number(summary.scores.overall).toFixed(1) : '-' }}
            </div>
            <div v-if="summary.scores?.tier?.next_label" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              距 {{ summary.scores.tier.next_label }} 还差 {{ Math.max(0, (summary.scores.tier.next_threshold ?? 0) - (summary.scores.overall ?? 0)) }} 分
            </div>
          </div>
        </div>
      </div>

      <!-- 周期选择 -->
      <div class="flex items-center gap-2 flex-wrap">
        <div class="flex items-center gap-1">
          <UButton
            size="sm"
            variant="outline"
            color="neutral"
            icon="i-heroicons-chevron-left"
            :disabled="isCustom"
            :title="`上一${periodUnitLabel}`"
            @click="period.shift(-1)"
          />
          <UButtonGroup>
            <UButton
              v-for="p in periods"
              :key="p.value"
              size="sm"
              :variant="activePeriod === p.value ? 'solid' : 'outline'"
              :color="activePeriod === p.value ? 'primary' : 'neutral'"
              @click="period.setPeriod(p.value)"
            >
              {{ p.label }}
            </UButton>
          </UButtonGroup>
          <UButton
            size="sm"
            variant="outline"
            color="neutral"
            icon="i-heroicons-chevron-right"
            :disabled="isCustom || periodOffset >= 0"
            :title="`下一${periodUnitLabel}`"
            @click="period.shift(1)"
          />
        </div>
        <UPopover>
          <UButton size="sm" variant="outline" color="neutral" icon="i-heroicons-calendar-days">
            {{ isCustom ? `${customStart} ~ ${customEnd}` : '自定义' }}
          </UButton>
          <template #content>
            <div class="p-3 space-y-3">
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">开始日期</label>
                <UInput v-model="customStart" type="date" size="sm" />
              </div>
              <div class="space-y-1">
                <label class="text-xs text-gray-500 dark:text-gray-400">结束日期</label>
                <UInput v-model="customEnd" type="date" size="sm" />
              </div>
              <UButton size="sm" block @click="applyCustomRange">应用</UButton>
            </div>
          </template>
        </UPopover>
      </div>

      <!-- 该周期暂无数据 -->
      <div v-if="!summary?.scores" class="bg-amber-50 dark:bg-amber-950 rounded-xl border border-amber-100 dark:border-amber-900 p-6 text-center">
        <UIcon name="i-heroicons-information-circle" class="w-8 h-8 text-amber-400 mx-auto mb-2" />
        <p class="text-sm text-amber-700 dark:text-amber-300">该周期暂无 KPI 数据，请先在团队页面刷新数据</p>
      </div>

      <!-- 标签页 -->
      <UTabs v-if="summary?.scores" v-model="activeTab" :items="tabs" class="w-full">
        <template #arena>
          <!-- 代码竞技场: 工单计件 + 重修 + SLA -->
          <div class="space-y-6 pt-4">
            <!-- 计件汇总 -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div
                v-for="card in arenaCards"
                :key="card.label"
                class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4"
              >
                <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ card.label }}</div>
                <div class="text-2xl font-bold" :class="card.colorClass">{{ card.value }}</div>
                <div v-if="card.sub" class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ card.sub }}</div>
              </div>
            </div>

            <!-- 工单规模分布 + 段位进度 -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">工单规模分布</h3>
                <div class="space-y-3">
                  <div v-for="bar in sizeBars" :key="bar.label" class="space-y-1">
                    <div class="flex items-center justify-between text-xs">
                      <span class="text-gray-700 dark:text-gray-300">{{ bar.label }}</span>
                      <span class="text-gray-500 dark:text-gray-400">{{ bar.count }} 个 · ¥{{ bar.unit_price_hint }}</span>
                    </div>
                    <div class="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div :class="bar.colorClass" :style="{ width: bar.pct + '%' }" class="h-full transition-all"></div>
                    </div>
                  </div>
                </div>
                <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 text-xs text-gray-400 dark:text-gray-500">
                  规则: 预计工时 &lt; 4h 走计件梯度 (前 20 个 ¥100, 21+ ¥160); 4-16h 中型 ¥250; ≥16h 大型 ¥600 (可在评分配置中调整)
                </div>
              </div>

              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">段位进度</h3>
                <div v-if="summary?.scores?.tier" class="space-y-4">
                  <div class="flex items-center justify-between">
                    <UBadge :class="tierBadgeClass(summary.scores.tier.key)" variant="subtle" size="lg">
                      <UIcon name="i-heroicons-trophy" class="w-4 h-4 mr-1" />
                      {{ summary.scores.tier.label }}
                    </UBadge>
                    <span class="text-xs text-gray-400 dark:text-gray-500">综合分 {{ Number(summary.scores.overall).toFixed(1) }}</span>
                  </div>
                  <div v-if="summary.scores.tier.next_label">
                    <div class="flex items-center justify-between text-xs mb-1">
                      <span class="text-gray-500 dark:text-gray-400">下一档: {{ summary.scores.tier.next_label }}</span>
                      <span class="text-gray-500 dark:text-gray-400">{{ Number(summary.scores.overall).toFixed(0) }} / {{ summary.scores.tier.next_threshold }}</span>
                    </div>
                    <div class="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-crystal-400 to-violet-500 transition-all"
                        :style="{ width: tierProgressPct + '%' }"
                      ></div>
                    </div>
                  </div>
                  <div v-else class="text-center text-sm text-gray-400 dark:text-gray-500 py-4">
                    已抵达最高段位 🎉
                  </div>
                </div>
              </div>
            </div>

            <!-- 重修 + 总延期 + 拖延度 + SLA -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">保护期 ({{ workload?.protection_days ?? 7 }} 天) 重修</h3>
                <div class="flex items-end gap-2">
                  <div class="text-4xl font-bold" :class="(workload?.rework_count ?? 0) > 0 ? 'text-red-500' : 'text-emerald-500'">
                    {{ workload?.rework_count ?? 0 }}
                  </div>
                  <div class="text-sm text-gray-400 dark:text-gray-500 pb-1">单</div>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">
                  Issue 在标记完成后 {{ workload?.protection_days ?? 7 }} 天内回到未完成状态,记为重修。
                </p>
              </div>
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">总延期时长</h3>
                <div class="flex items-end gap-2">
                  <div class="text-4xl font-bold" :class="(workload?.total_delay_hours ?? 0) > 0 ? 'text-red-500' : 'text-emerald-500'">
                    {{ workload?.total_delay_hours != null ? workload.total_delay_hours.toFixed(1) : '-' }}
                  </div>
                  <div class="text-sm text-gray-400 dark:text-gray-500 pb-1">小时</div>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">
                  本期 {{ workload?.over_estimate_count ?? 0 }} 单超出预计的累计延期时间。<br />
                  净偏差(含提前): {{ workload?.total_overrun_hours != null ? workload.total_overrun_hours.toFixed(1) : '-' }}h
                </p>
              </div>
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">平均拖延倍数</h3>
                <div class="flex items-end gap-2">
                  <div class="text-4xl font-bold" :class="delayColorClass">
                    {{ workload?.avg_delay_ratio ? workload.avg_delay_ratio.toFixed(2) : '-' }}
                  </div>
                  <div class="text-sm text-gray-400 dark:text-gray-500 pb-1">× 预计</div>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">
                  每单 actual/estimated 的平均值,反映单工单粒度的拖延倍率。
                </p>
              </div>
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">首次响应时间</h3>
                <div class="flex items-end gap-2">
                  <div class="text-4xl font-bold text-gray-900 dark:text-gray-100">
                    {{ workload?.avg_first_response_hours ? workload.avg_first_response_hours.toFixed(1) : '-' }}
                  </div>
                  <div class="text-sm text-gray-400 dark:text-gray-500 pb-1">小时</div>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">
                  Issue 创建到本人第一次操作的平均耗时,反映派单响应速度。
                </p>
              </div>
            </div>

            <!-- 明细 -->
            <div
              v-if="workload?.breakdown?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
            >
              <div class="px-5 py-3 border-b border-gray-50 dark:border-gray-800 flex items-center justify-between">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">本期完成工单明细</h3>
                <span class="text-xs text-gray-400">{{ workload.breakdown.length }} 条</span>
              </div>
              <UTable :data="workload.breakdown" :columns="breakdownColumns" :ui="{ th: 'text-xs', td: 'text-sm' }">
                <template #issue_id-cell="{ row }">
                  <NuxtLink :to="`/app/issues/${b(row).issue_id}`" class="text-crystal-500 hover:text-crystal-700 dark:text-crystal-400">
                    ISS-{{ String(b(row).issue_id).padStart(3, '0') }}
                  </NuxtLink>
                </template>
                <template #title-cell="{ row }">
                  <span class="line-clamp-1 max-w-md inline-block align-bottom">{{ b(row).title }}</span>
                </template>
                <template #size-cell="{ row }">
                  <UBadge :class="sizeBadgeClass(b(row).size)" variant="subtle" size="xs">
                    {{ b(row).size }}
                  </UBadge>
                </template>
                <template #estimated_hours-cell="{ row }">
                  {{ b(row).estimated_hours ? Number(b(row).estimated_hours).toFixed(1) : '-' }}h
                </template>
                <template #actual_hours-cell="{ row }">
                  <span v-if="b(row).actual_hours != null">{{ Number(b(row).actual_hours).toFixed(1) }}h</span>
                  <span v-else class="text-gray-400">-</span>
                </template>
                <template #delay_hours-cell="{ row }">
                  <span v-if="b(row).delay_hours != null" :class="rowDelayHoursClass(b(row).delay_hours!)">
                    {{ b(row).delay_hours! > 0 ? '+' : '' }}{{ b(row).delay_hours!.toFixed(1) }}h
                  </span>
                  <span v-else class="text-gray-400">-</span>
                </template>
                <template #delay_ratio-cell="{ row }">
                  <span v-if="b(row).delay_ratio != null" :class="rowDelayClass(b(row).delay_ratio!)">
                    {{ b(row).delay_ratio!.toFixed(2) }}×
                  </span>
                  <span v-else class="text-gray-400">-</span>
                </template>
                <template #price-cell="{ row }">
                  <span class="text-emerald-600 dark:text-emerald-400 font-medium">¥{{ b(row).price }}</span>
                </template>
              </UTable>
            </div>
            <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
              <UIcon name="i-heroicons-document-text" class="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
              <p class="text-sm text-gray-500 dark:text-gray-400">本期暂无完成工单</p>
            </div>
          </div>
        </template>

        <template #issues>
          <!-- 问题指标 -->
          <div class="space-y-6 pt-4">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- 雷达图 -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">能力雷达</h3>
                <ChartsRadarChart
                  :indicators="radarIndicators"
                  :values="radarValues"
                  :height="280"
                />
              </div>
              <!-- 指标卡片 -->
              <div class="grid grid-cols-2 gap-3 content-start">
                <div
                  v-for="card in issueMetricCards"
                  :key="card.label"
                  class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4"
                >
                  <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ card.label }}</div>
                  <div class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ card.value }}</div>
                  <div v-if="card.sub" class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ card.sub }}</div>
                </div>
              </div>
            </div>
            <!-- 优先级分布表 -->
            <div
              v-if="issues?.priority_breakdown?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
            >
              <div class="px-5 py-3 border-b border-gray-50 dark:border-gray-800">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">优先级分布</h3>
              </div>
              <UTable :data="issues.priority_breakdown" :columns="priorityColumns" :ui="{ th: 'text-xs', td: 'text-sm' }" />
            </div>
          </div>

        </template>
        <template #commits>
          <!-- Commit 分析 -->
          <div class="space-y-6 pt-4">
            <!-- 汇总卡片 -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div
                v-for="card in commitSummaryCards"
                :key="card.label"
                class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4"
              >
                <div class="text-xs text-gray-400 dark:text-gray-500 mb-1">{{ card.label }}</div>
                <div class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ card.value }}</div>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- 提交类型分布 -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">提交类型分布</h3>
                <ChartsPieChart
                  :data="commitTypePieData"
                  :height="260"
                />
              </div>
              <!-- 提交大小分布 -->
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">提交大小分布</h3>
                <ChartsBarChart
                  :x-data="['小(<50行)', '中(50-200行)', '大(>200行)']"
                  :series="[{ name: '提交数', data: commitSizeData }]"
                  :height="260"
                />
              </div>
            </div>

            <!-- 技术栈 -->
            <div
              v-if="commits?.tech_stack_breadth?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
            >
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">技术栈广度</h3>
              <div class="flex flex-wrap gap-2">
                <UBadge
                  v-for="tech in commits.tech_stack_breadth"
                  :key="tech"
                  color="primary"
                  variant="subtle"
                  size="sm"
                >
                  {{ tech }}
                </UBadge>
              </div>
            </div>

            <!-- 工作节奏 -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">每日提交分布</h3>
                <ChartsBarChart
                  :x-data="hourLabels"
                  :series="[{ name: '提交数', data: byHourData }]"
                  :height="220"
                />
              </div>
              <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">每周提交分布</h3>
                <ChartsBarChart
                  :x-data="weekdayLabels"
                  :series="[{ name: '提交数', data: byWeekdayData }]"
                  :height="220"
                />
              </div>
            </div>

            <!-- 仓库覆盖 -->
            <div
              v-if="commits?.repo_coverage?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
            >
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">仓库覆盖</h3>
              <div class="space-y-2">
                <div
                  v-for="repo in commits.repo_coverage"
                  :key="repo.repo_name || repo.name"
                  class="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-2.5"
                >
                  <span class="text-sm text-gray-700 dark:text-gray-300">{{ repo.repo_name || repo.name }}</span>
                  <span class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ repo.commit_count ?? repo.count }} 次提交</span>
                </div>
              </div>
            </div>
          </div>

        </template>
        <template #trends>
          <!-- 趋势变化 -->
          <div class="space-y-6 pt-4">
            <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">各维度趋势</h3>
              <ChartsLineChart
                v-if="trendXData.length"
                :x-data="trendXData"
                :series="trendSeries"
                :height="340"
              />
              <div v-else class="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
                暂无趋势数据
              </div>
            </div>
          </div>

        </template>
        <template #suggestions>
          <!-- 改进建议 -->
          <div class="space-y-6 pt-4">
            <!-- 画像 -->
            <div
              v-if="suggestions?.profile"
              class="rounded-xl p-6 text-center bg-gradient-to-r from-crystal-500 to-violet-500"
            >
              <div class="text-lg font-semibold text-white">{{ suggestions.profile }}</div>
            </div>

            <!-- 不足 -->
            <div
              v-if="suggestions?.shortcomings?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
            >
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">待改进项</h3>
              <div class="space-y-3">
                <div
                  v-for="(item, idx) in suggestions.shortcomings"
                  :key="idx"
                  class="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
                >
                  <span
                    class="inline-block w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                    :class="severityDotClass(item.severity)"
                  />
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ item.title || item.dimension }}</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ item.description || item.detail }}</div>
                  </div>
                  <UBadge
                    :color="severityBadgeColor(item.severity)"
                    variant="subtle"
                    size="xs"
                  >
                    {{ severityLabel(item.severity) }}
                  </UBadge>
                </div>
              </div>
            </div>

            <!-- 趋势建议 -->
            <div
              v-if="suggestions?.trends?.length"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5"
            >
              <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">趋势观察</h3>
              <div class="space-y-3">
                <div
                  v-for="(t, idx) in suggestions.trends"
                  :key="idx"
                  class="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800"
                >
                  <UIcon
                    :name="t.direction === 'up' ? 'i-heroicons-arrow-trending-up' : 'i-heroicons-arrow-trending-down'"
                    class="w-5 h-5 mt-0.5 flex-shrink-0"
                    :class="t.direction === 'up' ? 'text-emerald-500' : 'text-red-500'"
                  />
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ t.dimension || t.title }}</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ t.description || t.detail }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 无建议 -->
            <div
              v-if="!suggestions?.shortcomings?.length && !suggestions?.trends?.length && !suggestions?.profile"
              class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center"
            >
              <UIcon name="i-heroicons-light-bulb" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
              <p class="text-gray-500 dark:text-gray-400">暂无改进建议</p>
            </div>
          </div>
        </template>
      </UTabs>
    </template>

    <!-- 无数据 -->
    <div
      v-else-if="!loading"
      class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center"
    >
      <UIcon name="i-heroicons-chart-bar" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
      <p class="text-gray-500 dark:text-gray-400">暂无该用户的 KPI 数据</p>
      <NuxtLink to="/app/kpi">
        <UButton class="mt-4" size="sm" variant="outline" color="neutral">返回团队 KPI</UButton>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'default' })

const route = useRoute()
const { api } = useApi()
const { resolveAvatarUrl } = useAvatars()
const { user: authUser } = useAuth()

const loading = ref(true)
const activeTab = ref('arena')

const period = usePeriodRange('month')
const { activePeriod, customStart, customEnd, isCustom, periodOffset } = period

const summary = ref<any>(null)
const issues = ref<any>(null)
const commits = ref<any>(null)
const workload = ref<any>(null)
const trends = ref<any>(null)
const suggestions = ref<any>(null)

const periods = [
  { label: '周', value: 'week' as const },
  { label: '月', value: 'month' as const },
  { label: '季度', value: 'quarter' as const },
]

const periodUnitLabel = computed(() => {
  if (activePeriod.value === 'week') return '周'
  if (activePeriod.value === 'quarter') return '季度'
  return '月'
})

const tabs = [
  { label: '代码竞技场', value: 'arena', slot: 'arena' },
  { label: '问题指标', value: 'issues', slot: 'issues' },
  { label: 'Commit 分析', value: 'commits', slot: 'commits' },
  { label: '趋势变化', value: 'trends', slot: 'trends' },
  { label: '改进建议', value: 'suggestions', slot: 'suggestions' },
]

// 解析用户 ID，支持 'me' 别名
const userId = computed(() => {
  const id = route.params.id as string
  if (id === 'me') return authUser.value?.id
  return id
})

// 雷达图数据
const radarIndicators = computed(() => [
  { name: '效率', max: 100 },
  { name: '产出', max: 100 },
  { name: '质量', max: 100 },
  { name: '能力', max: 100 },
  { name: '成长', max: 100 },
])

const radarValues = computed(() => {
  const s = summary.value?.scores
  if (!s) return [0, 0, 0, 0, 0]
  return [
    Number(s.efficiency) || 0,
    Number(s.output) || 0,
    Number(s.quality) || 0,
    Number(s.capability) || 0,
    Number(s.growth) || 0,
  ]
})

// Code Arena 汇总卡片
const arenaCards = computed(() => {
  const w = workload.value
  if (!w) return []
  return [
    { label: '完成工单', value: w.completed_count ?? 0, colorClass: 'text-violet-600 dark:text-violet-400', sub: `${w.small_count ?? 0} 小 / ${w.medium_count ?? 0} 中 / ${w.large_count ?? 0} 大` },
    { label: '估算计件', value: `¥${w.estimated_earnings ?? 0}`, colorClass: 'text-emerald-600 dark:text-emerald-400', sub: '按预计工时分级' },
    { label: '保护期重修', value: w.rework_count ?? 0, colorClass: (w.rework_count ?? 0) > 0 ? 'text-red-500' : 'text-gray-900 dark:text-gray-100', sub: `${w.protection_days ?? 7} 天窗口` },
    { label: '协助修复', value: w.protection_helper_count ?? 0, colorClass: 'text-sky-600 dark:text-sky-400', sub: '帮助他人解决' },
  ]
})

const delayColorClass = computed(() => {
  const r = workload.value?.avg_delay_ratio
  if (!r) return 'text-gray-900 dark:text-gray-100'
  if (r > 1.5) return 'text-red-500'
  if (r > 1.1) return 'text-amber-500'
  if (r < 0.9) return 'text-emerald-500'
  return 'text-gray-900 dark:text-gray-100'
})

function rowDelayClass(ratio: number) {
  if (ratio > 1.5) return 'text-red-500 font-medium'
  if (ratio > 1.1) return 'text-amber-500'
  if (ratio < 0.9) return 'text-emerald-500'
  return ''
}

function rowDelayHoursClass(hours: number) {
  if (hours > 8) return 'text-red-500 font-medium'
  if (hours > 0) return 'text-amber-500'
  if (hours < 0) return 'text-emerald-500'
  return ''
}

const sizeBars = computed(() => {
  const w = workload.value
  if (!w) return []
  const total = (w.small_count ?? 0) + (w.medium_count ?? 0) + (w.large_count ?? 0)
  const pct = (n: number) => total > 0 ? Math.round(n / total * 100) : 0
  return [
    { label: '小型 (预计 < 4h)', count: w.small_count ?? 0, pct: pct(w.small_count ?? 0), colorClass: 'bg-violet-400', unit_price_hint: '100-160' },
    { label: '中型 (预计 4-16h)', count: w.medium_count ?? 0, pct: pct(w.medium_count ?? 0), colorClass: 'bg-amber-400', unit_price_hint: '250' },
    { label: '大型 (预计 ≥ 16h)', count: w.large_count ?? 0, pct: pct(w.large_count ?? 0), colorClass: 'bg-rose-400', unit_price_hint: '600' },
  ]
})

const tierProgressPct = computed(() => {
  const t = summary.value?.scores?.tier
  const overall = summary.value?.scores?.overall ?? 0
  if (!t || t.next_threshold == null) return 100
  const range = t.next_threshold - (t.threshold ?? 0)
  if (range <= 0) return 100
  const progress = Math.max(0, overall - (t.threshold ?? 0))
  return Math.min(100, Math.round(progress / range * 100))
})

const breakdownColumns = [
  { accessorKey: 'issue_id', header: '编号' },
  { accessorKey: 'title', header: '标题' },
  { accessorKey: 'size', header: '规模' },
  { accessorKey: 'estimated_hours', header: '预计' },
  { accessorKey: 'actual_hours', header: '实际' },
  { accessorKey: 'delay_hours', header: '延期' },
  { accessorKey: 'delay_ratio', header: '倍数' },
  { accessorKey: 'price', header: '单价' },
]

function tierBadgeClass(key: string) {
  const map: Record<string, string> = {
    bronze: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
    silver: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
    gold: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    platinum: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
    diamond: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
    master: 'bg-gradient-to-r from-violet-200 to-pink-200 text-violet-800 dark:from-violet-900/60 dark:to-pink-900/60 dark:text-violet-200',
  }
  return map[key] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'
}

interface BreakdownRow {
  issue_id: number
  title: string
  size: string
  estimated_hours: number
  actual_hours: number | null
  delay_ratio: number | null
  delay_hours: number | null
  price: number
}

function b(row: any): BreakdownRow {
  return row.original as BreakdownRow
}

function sizeBadgeClass(size: string) {
  if (size === '大型') return 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300'
  if (size === '中型') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
  return 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'
}

// 问题指标卡片
const issueMetricCards = computed(() => {
  if (!issues.value) return []
  const d = issues.value
  return [
    { label: '分配问题数', value: d.assigned_count ?? '-' },
    { label: '已解决', value: d.resolved_count ?? '-', sub: d.resolution_rate != null ? `解决率 ${(d.resolution_rate * 100).toFixed(0)}%` : undefined },
    { label: '平均解决时间', value: d.avg_resolution_hours != null ? `${d.avg_resolution_hours.toFixed(1)}h` : '-' },
    { label: '日均解决', value: d.daily_resolved_avg != null ? d.daily_resolved_avg.toFixed(1) : '-' },
    { label: '加权问题价值', value: d.weighted_issue_value != null ? d.weighted_issue_value.toFixed(1) : '-' },
  ]
})

const priorityColumns = [
  { accessorKey: 'priority', header: '优先级' },
  { accessorKey: 'count', header: '数量' },
  { accessorKey: 'resolved', header: '已解决' },
  { accessorKey: 'avg_hours', header: '平均耗时' },
]

// Commit 汇总卡片
const commitSummaryCards = computed(() => {
  if (!commits.value) return []
  const c = commits.value
  return [
    { label: '总提交数', value: c.total_commits ?? '-' },
    { label: '代码变更', value: c.additions != null && c.deletions != null ? `+${c.additions} / -${c.deletions}` : '-' },
    { label: '自引 Bug 率', value: c.self_introduced_bug_rate != null ? `${(c.self_introduced_bug_rate * 100).toFixed(1)}%` : '-' },
    { label: 'Churn 率', value: c.churn_rate != null ? `${(c.churn_rate * 100).toFixed(1)}%` : '-' },
  ]
})

// 提交类型饼图
const commitTypePieData = computed(() => {
  const dist = commits.value?.commit_type_distribution
  if (!dist || typeof dist !== 'object') return []
  return Object.entries(dist).map(([name, value]) => ({ name, value: value as number }))
})

// 提交大小柱状图
const commitSizeData = computed(() => {
  const dist = commits.value?.commit_size_distribution
  if (!dist) return [0, 0, 0]
  return [dist.small ?? 0, dist.medium ?? 0, dist.large ?? 0]
})

// 工作节奏
const hourLabels = Array.from({ length: 24 }, (_, i) => `${i}时`)
const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const byHourData = computed(() => {
  const bh = commits.value?.by_hour
  if (!bh) return Array(24).fill(0)
  if (Array.isArray(bh)) return bh
  return Array.from({ length: 24 }, (_, i) => bh[String(i)] ?? 0)
})

const byWeekdayData = computed(() => {
  const bw = commits.value?.by_weekday
  if (!bw) return Array(7).fill(0)
  if (Array.isArray(bw)) return bw
  return Array.from({ length: 7 }, (_, i) => bw[String(i)] ?? 0)
})

// 趋势图
const trendXData = computed(() => {
  if (!trends.value?.history?.length) return []
  return trends.value.history.map((h: any) => h.period_start?.slice(5) || '')
})

const trendSeries = computed<{ name: string; data: number[] }[]>(() => {
  if (!trends.value?.history?.length) return []
  const dims = ['efficiency', 'output', 'quality', 'capability', 'growth'] as const
  const labels: Record<string, string> = { efficiency: '效率', output: '产出', quality: '质量', capability: '能力', growth: '成长' }
  return dims.map(dim => ({
    name: labels[dim]!,
    data: trends.value.history.map((h: any) => Number(h.scores?.[dim]) || 0),
  }))
})

// 建议相关
function severityDotClass(severity: string) {
  if (severity === 'high') return 'bg-red-500'
  if (severity === 'medium') return 'bg-amber-500'
  return 'bg-gray-400'
}

function severityBadgeColor(severity: string): any {
  if (severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'neutral'
}

function severityLabel(severity: string) {
  if (severity === 'high') return '高'
  if (severity === 'medium') return '中'
  return '低'
}

// 数据加载
function buildQuery() {
  return period.toQuery()
}

function applyCustomRange() {
  period.applyCustom()
  fetchAll()
}

async function fetchAll() {
  const uid = userId.value
  if (!uid) return

  loading.value = true
  const q = buildQuery()

  try {
    const [summaryRes, issuesRes, commitsRes, workloadRes, trendsRes, suggestionsRes] = await Promise.all([
      api<any>(`/api/kpi/users/${uid}/summary/?${q}`).catch(() => null),
      api<any>(`/api/kpi/users/${uid}/issues/?${q}`).catch(() => null),
      api<any>(`/api/kpi/users/${uid}/commits/?${q}`).catch(() => null),
      api<any>(`/api/kpi/users/${uid}/workload/?${q}`).catch(() => null),
      api<any>(`/api/kpi/users/${uid}/trends/?periods=6`).catch(() => null),
      api<any>(`/api/kpi/users/${uid}/suggestions/?${q}`).catch(() => null),
    ])
    // 切换周期时保留用户基本信息，仅更新分数和指标
    if (summaryRes) {
      summary.value = summaryRes
    } else if (summary.value) {
      summary.value = { ...summary.value, scores: null, rankings: null }
    }
    issues.value = issuesRes
    commits.value = commitsRes
    workload.value = workloadRes
    trends.value = trendsRes
    suggestions.value = suggestionsRes
  } catch (e) {
    console.error('Failed to load KPI profile:', e)
  } finally {
    loading.value = false
  }
}

watch([activePeriod, periodOffset], () => {
  fetchAll()
})

onMounted(fetchAll)
</script>
