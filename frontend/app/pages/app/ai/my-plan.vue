<template>
  <div class="space-y-6">
    <div class="flex items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">我的任务</h1>
        <p class="text-sm text-gray-400 dark:text-gray-500 mt-0.5">{{ currentPeriod }} · 派发给你的任务与点评</p>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
      <UIcon name="i-heroicons-clipboard-document-list" class="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-3 animate-pulse" />
      <p class="text-gray-500 dark:text-gray-400">加载中...</p>
    </div>

    <!-- 暂无任务（仍展示历史） -->
    <template v-else>
      <template v-if="current">
        <!-- 汇总卡片（点击可筛选） -->
        <div class="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <button
            v-for="f in filters"
            :key="f.value ?? 'all'"
            type="button"
            class="text-left rounded-xl border p-4 transition-colors"
            :class="filterStatus === f.value
              ? 'border-crystal-400 dark:border-crystal-600 ring-1 ring-crystal-300 dark:ring-crystal-700 bg-crystal-50/50 dark:bg-crystal-950/20'
              : 'border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-gray-200 dark:hover:border-gray-700'"
            @click="toggleFilter(f.value)"
          >
            <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1 truncate">{{ f.label }}</p>
            <p class="text-2xl font-bold tabular-nums" :class="f.color">{{ f.count }}</p>
          </button>

          <!-- 完成进度 -->
          <div class="col-span-2 lg:col-span-1 bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-4 flex flex-col">
            <div class="flex items-baseline justify-between mb-2">
              <p class="text-xs font-medium text-gray-400 dark:text-gray-500">完成进度</p>
              <p class="text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-100">{{ doneCount }} / {{ actionItems.length }}</p>
            </div>
            <div class="mt-auto">
              <div class="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div
                  class="h-full rounded-full bg-gradient-to-r from-crystal-500 to-emerald-500 transition-[width] duration-700 ease-out"
                  :style="{ width: progressPct + '%' }"
                />
              </div>
              <p class="text-[11px] mt-1.5 tabular-nums" :class="overdueCount > 0 ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-400 dark:text-gray-500'">
                {{ Math.round(progressPct) }}%<span v-if="overdueCount > 0"> · {{ overdueCount }} 项逾期</span>
              </p>
            </div>
          </div>
        </div>

        <!-- 本月评价（经理公开给你的评价） -->
        <div
          v-if="current.employee_evaluation"
          class="bg-white dark:bg-gray-900 rounded-xl border border-crystal-100 dark:border-crystal-900/50 p-5"
        >
          <div class="flex items-center gap-2 mb-2">
            <UIcon name="i-heroicons-chat-bubble-bottom-center-text" class="w-4 h-4 text-crystal-500" />
            <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">本月评价</h3>
          </div>
          <MarkdownView :text="current.employee_evaluation" />
        </div>

        <!-- 行动项列表 -->
        <div class="space-y-3">
          <div v-if="!filteredItems.length" class="bg-white dark:bg-gray-900 rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-8 text-center text-sm text-gray-400 dark:text-gray-500">
            该筛选下暂无任务
          </div>
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="rounded-xl border overflow-hidden transition-shadow hover:shadow-sm"
            :class="item.status === 'not_achieved'
              ? 'bg-red-50/60 dark:bg-red-950/20 border-red-200 dark:border-red-900/50'
              : 'bg-white dark:bg-gray-900 border-gray-100 dark:border-gray-800'"
          >
            <!-- 标题行（可点击展开） -->
            <div
              class="p-4 cursor-pointer flex items-center justify-between gap-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
              @click="toggleExpand(item.id)"
            >
              <div class="flex items-center gap-3 min-w-0">
                <UIcon
                  :name="expandedItems.has(item.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                  class="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0"
                />
                <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="priorityDot(item.priority)" />
                <span class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ item.title }}</span>
              </div>
              <div class="flex items-center gap-2.5 flex-shrink-0">
                <span
                  v-if="item.due_date"
                  class="text-xs tabular-nums hidden sm:inline"
                  :class="isOverdue(item) ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-400 dark:text-gray-500'"
                >
                  <UIcon v-if="isOverdue(item)" name="i-heroicons-exclamation-triangle" class="w-3 h-3 inline -mt-0.5" />
                  {{ item.due_date }}
                </span>
                <UBadge :color="statusColor(item.status)" variant="subtle" size="xs">
                  {{ statusLabel(item.status) }}
                </UBadge>
              </div>
            </div>

            <!-- 展开内容 -->
            <div v-if="expandedItems.has(item.id)" class="border-t border-gray-100 dark:border-gray-800 p-4 space-y-4">
              <div v-if="item.description">
                <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">描述</p>
                <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ item.description }}</p>
              </div>

              <div v-if="item.measurable_target">
                <p class="text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">可量化目标</p>
                <p class="text-sm text-gray-700 dark:text-gray-300">{{ item.measurable_target }}</p>
              </div>

              <!-- 我的执行计划（开始执行时的承诺） -->
              <div v-if="item.start_plan" class="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40 p-3">
                <div class="flex items-center justify-between gap-2 mb-1">
                  <p class="text-xs font-medium text-gray-400 dark:text-gray-500">我的执行计划</p>
                  <span v-if="item.self_eta" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">我预计 {{ item.self_eta }} 完成</span>
                </div>
                <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ item.start_plan }}</p>
              </div>

              <!-- 状态操作 -->
              <div>
                <UButton
                  v-if="item.status === 'pending'"
                  size="sm"
                  color="primary"
                  icon="i-heroicons-play"
                  :loading="updatingStatus[item.id]"
                  @click.stop="openStart(item)"
                >
                  开始执行
                </UButton>
                <UButton
                  v-else-if="item.status === 'in_progress'"
                  size="sm"
                  color="success"
                  icon="i-heroicons-check"
                  :loading="updatingStatus[item.id]"
                  @click.stop="openSubmit(item)"
                >
                  提交完成
                </UButton>
                <div v-else-if="item.status === 'submitted'" class="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                  <UIcon name="i-heroicons-clock" class="w-4 h-4" />
                  <span>已提交，等待验收</span>
                </div>
                <div v-else-if="item.status === 'not_achieved'" class="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                  <UIcon name="i-heroicons-x-circle" class="w-4 h-4" />
                  <span>未达成</span>
                </div>
              </div>

              <!-- 我的复盘与自评（提交后可见） -->
              <div
                v-if="item.self_assessment"
                class="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-800/40 p-3.5 space-y-2.5"
              >
                <div class="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                  <UIcon name="i-heroicons-pencil-square" class="w-3.5 h-3.5" />
                  我的复盘
                </div>
                <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ item.self_assessment }}</p>
                <div
                  v-if="item.self_scores && Object.keys(item.self_scores).length"
                  class="pt-2.5 border-t border-gray-100 dark:border-gray-700/50 space-y-1.5"
                >
                  <p class="text-xs text-gray-400 dark:text-gray-500">我的自评</p>
                  <div
                    v-for="d in (item.review_dimensions || [])"
                    :key="d.key"
                    class="flex items-center justify-between gap-2 text-sm"
                  >
                    <span class="text-gray-500 dark:text-gray-400">{{ d.label }}</span>
                    <StarRow :value="item.self_scores?.[d.key] || 0" />
                  </div>
                </div>
              </div>

              <!-- 经理点评 / 未达成（含自评对比、归因、改进闭环） -->
              <div
                v-if="hasReview(item)"
                class="rounded-lg border p-3.5 space-y-2.5"
                :class="item.status === 'not_achieved'
                  ? 'border-red-200 dark:border-red-900/50 bg-red-50/50 dark:bg-red-950/20'
                  : 'border-crystal-100 dark:border-crystal-900/50 bg-crystal-50/40 dark:bg-crystal-950/20'"
              >
                <div class="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
                  <UIcon :name="item.status === 'not_achieved' ? 'i-heroicons-x-circle' : 'i-heroicons-star'" class="w-3.5 h-3.5" :class="item.status === 'not_achieved' ? 'text-red-500' : 'text-amber-500'" />
                  {{ item.status === 'not_achieved' ? '未达成' : '经理点评' }}
                  <UBadge v-if="item.status === 'not_achieved' && item.not_achieved_reason_display" color="error" variant="subtle" size="xs">{{ item.not_achieved_reason_display }}</UBadge>
                  <span v-if="item.reviewed_by_name" class="font-normal text-gray-400 dark:text-gray-500">· {{ item.reviewed_by_name }}</span>
                </div>
                <div v-if="item.status === 'verified'" class="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-1.5 text-sm items-center">
                  <span class="text-xs text-gray-400 dark:text-gray-500" />
                  <span class="text-xs text-gray-400 dark:text-gray-500 text-center">自评</span>
                  <span class="text-xs text-gray-400 dark:text-gray-500 text-center">经理</span>
                  <template v-for="d in (item.review_dimensions || [])" :key="d.key">
                    <span class="text-gray-500 dark:text-gray-400 truncate">{{ d.label }}</span>
                    <StarRow :value="item.self_scores?.[d.key] || 0" size="xs" />
                    <StarRow :value="item.scores?.[d.key] || 0" />
                  </template>
                </div>
                <div v-if="item.review_comment" class="text-sm text-gray-700 dark:text-gray-300 border-t border-gray-100 dark:border-gray-700/40 pt-2.5">
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ item.status === 'not_achieved' ? '原因：' : '总评：' }}</span>{{ item.review_comment }}
                </div>

                <!-- 闭环：员工确认 + 改进措施 -->
                <div v-if="item.status === 'not_achieved'" class="border-t border-gray-100 dark:border-gray-700/40 pt-2.5">
                  <div v-if="item.acknowledged" class="text-sm text-gray-700 dark:text-gray-300">
                    <span class="text-xs text-emerald-600 dark:text-emerald-400">✓ 已确认 · 我的改进措施：</span>{{ item.improve_note || '—' }}
                  </div>
                  <div v-else class="space-y-2">
                    <p class="text-xs font-medium text-gray-500 dark:text-gray-400">请确认并写下改进措施（下次怎么做得更好）</p>
                    <UTextarea v-model="ackNote[item.id]" :rows="2" placeholder="例如：先查日志定位根因，遇阻塞 2 小时内主动提出…" class="w-full" />
                    <UButton size="sm" color="primary" icon="i-heroicons-check" :loading="ackSubmitting[item.id]" :disabled="!ackNote[item.id]?.trim()" @click.stop="acknowledge(item.id)">
                      确认并提交改进
                    </UButton>
                  </div>
                </div>
              </div>

              <!-- 评论列表 -->
              <div v-if="item.comments && item.comments.length" class="space-y-2">
                <p class="text-xs font-medium text-gray-400 dark:text-gray-500">反馈记录</p>
                <div
                  v-for="c in item.comments"
                  :key="c.id"
                  class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3"
                >
                  <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{{ c.author_name }}</span>
                    <span class="text-xs text-gray-400 dark:text-gray-500">{{ formatDate(c.created_at) }}</span>
                  </div>
                  <p class="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">{{ c.content }}</p>
                  <img
                    v-if="c.attachment_url"
                    :src="c.attachment_url"
                    class="mt-2 max-w-xs rounded border border-gray-200 dark:border-gray-700"
                    alt="附件"
                  >
                </div>
              </div>

              <!-- 评论表单 -->
              <div class="flex gap-2">
                <UInput
                  v-model="commentText[item.id]"
                  placeholder="补充反馈..."
                  class="flex-1"
                  size="sm"
                  @keydown.enter.prevent="addComment(item.id)"
                />
                <UButton
                  size="sm"
                  variant="soft"
                  icon="i-heroicons-paper-airplane"
                  :loading="submittingComment[item.id]"
                  :disabled="!commentText[item.id]?.trim()"
                  @click.stop="addComment(item.id)"
                >
                  发送
                </UButton>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 当月暂无任务 -->
      <div v-else class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-12 text-center">
        <UIcon name="i-heroicons-clipboard-document-list" class="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
        <p class="text-gray-500 dark:text-gray-400">本月暂无派发给你的任务</p>
      </div>

      <!-- 立计划对话框（开始执行时的承诺） -->
      <UModal v-model:open="startModalOpen" :ui="{ content: 'sm:max-w-md' }">
        <template #content>
          <div class="p-5 space-y-4">
            <div>
              <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">开始执行</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ startItem?.title }}</p>
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">
                我打算怎么做 <span class="text-red-500">*</span>
              </label>
              <p class="text-[11px] text-gray-400 dark:text-gray-500 -mt-0.5">一两句你自己的思路即可，不要照抄任务描述</p>
              <UTextarea v-model="startPlan" :rows="3" placeholder="例如：先排查日志定位根因，再改 X，最后补一个回归用例…" class="w-full" />
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">
                我预计完成日期 <span class="text-red-500">*</span>
              </label>
              <UInput v-model="startEta" type="date" class="w-full" />
            </div>

            <div class="flex justify-end gap-2 pt-1">
              <UButton variant="ghost" color="neutral" @click="startModalOpen = false">取消</UButton>
              <UButton color="primary" icon="i-heroicons-play" :loading="startItem && updatingStatus[startItem.id]" @click="confirmStart">开始执行</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- 提交完成对话框（结构化复盘 + 自评） -->
      <UModal v-model:open="submitModalOpen" :ui="{ content: 'sm:max-w-lg' }">
        <template #content>
          <div class="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
            <div>
              <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">提交完成</h3>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ submitItem?.title }}</p>
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">成果说明（做了什么，可附链接/截图，可留空）</label>
              <UTextarea v-model="submitOutcome" :rows="2" placeholder="例如：完成了 X，PR 链接…" class="w-full" />
            </div>

            <div class="space-y-1">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">
                我的思考与判断 <span class="text-red-500">*</span>
              </label>
              <p class="text-[11px] text-gray-400 dark:text-gray-500 -mt-0.5">尤其：你对 AI 输出做了哪些验证/发现了什么问题/哪些是你自己的判断</p>
              <UTextarea v-model="submitReflection" :rows="4" placeholder="写出你自己的分析、踩过的坑、为什么这么做…" class="w-full" />
            </div>

            <div v-if="(submitItem?.review_dimensions || []).length" class="space-y-2">
              <label class="text-xs font-medium text-gray-500 dark:text-gray-400">
                自评 <span class="text-red-500">*</span>
                <span class="font-normal text-gray-400 dark:text-gray-500">（先给自己打分，再由经理点评）</span>
              </label>
              <div
                v-for="d in submitItem.review_dimensions"
                :key="d.key"
                class="flex items-center gap-2"
              >
                <span class="text-sm text-gray-600 dark:text-gray-400 w-24 flex-shrink-0 truncate">{{ d.label }}</span>
                <UButton
                  v-for="star in 5"
                  :key="star"
                  size="xs"
                  variant="ghost"
                  :color="(submitSelfScores[d.key] || 0) >= star ? 'warning' : 'neutral'"
                  icon="i-heroicons-star-solid"
                  @click="submitSelfScores[d.key] = star"
                />
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-1">
              <UButton variant="ghost" color="neutral" @click="submitModalOpen = false">取消</UButton>
              <UButton color="success" :loading="submitItem && updatingStatus[submitItem.id]" @click="confirmSubmit">确认提交</UButton>
            </div>
          </div>
        </template>
      </UModal>

      <!-- 过往月份 -->
      <div v-if="history.length" class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-gray-100 dark:border-gray-800">
          <UIcon name="i-heroicons-archive-box" class="w-4 h-4 text-gray-400 dark:text-gray-500" />
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">过往月份</h3>
          <UBadge color="neutral" variant="subtle" size="xs">{{ history.length }}</UBadge>
        </div>

        <div>
          <div
            v-for="h in history"
            :key="h.period"
            class="border-b border-gray-50 dark:border-gray-800/50 last:border-0"
          >
            <!-- 月份行 -->
            <button
              type="button"
              class="w-full flex items-center justify-between gap-3 px-5 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors"
              @click="toggleHistory(h.period)"
            >
              <div class="flex items-center gap-2.5 min-w-0">
                <UIcon
                  :name="historyOpen.has(h.period) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                  class="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0"
                />
                <span class="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-100">{{ h.period }}</span>
                <UBadge :color="h.status === 'archived' ? 'neutral' : 'success'" variant="subtle" size="xs">
                  {{ h.status === 'archived' ? '已归档' : '已发布' }}
                </UBadge>
              </div>
              <div class="flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
                <span class="tabular-nums">{{ h.item_count }} 项</span>
                <span class="tabular-nums text-emerald-600 dark:text-emerald-400">{{ h.done_count }} 已完成</span>
              </div>
            </button>

            <!-- 月份任务（懒加载） -->
            <div v-if="historyOpen.has(h.period)" class="px-5 pb-4 pl-11 space-y-2">
              <div v-if="historyLoading.has(h.period)" class="py-3 text-xs text-gray-400 dark:text-gray-500">加载中...</div>
              <template v-else-if="historyDetails[h.period]?.action_items?.length">
                <div
                  v-for="t in historyDetails[h.period].action_items"
                  :key="t.id"
                  class="rounded-lg border border-gray-100 dark:border-gray-800 p-3"
                >
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                      <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="priorityDot(t.priority)" />
                      <span class="text-sm text-gray-800 dark:text-gray-200 truncate">{{ t.title }}</span>
                    </div>
                    <div class="flex items-center gap-2 flex-shrink-0">
                      <span v-if="t.due_date" class="text-xs text-gray-400 dark:text-gray-500 tabular-nums hidden sm:inline">{{ t.due_date }}</span>
                      <UBadge :color="statusColor(t.status)" variant="subtle" size="xs">{{ statusLabel(t.status) }}</UBadge>
                    </div>
                  </div>
                  <!-- 历史点评（只读） -->
                  <div v-if="hasReview(t)" class="mt-2.5 pt-2.5 border-t border-gray-50 dark:border-gray-800 space-y-1.5">
                    <div
                      v-for="d in (t.review_dimensions || [])"
                      :key="d.key"
                      class="flex items-center justify-between gap-2 text-xs"
                    >
                      <span class="text-gray-500 dark:text-gray-400">{{ d.label }}</span>
                      <StarRow :value="t.scores?.[d.key] || 0" size="xs" />
                    </div>
                    <p v-if="t.review_comment" class="text-xs text-gray-600 dark:text-gray-400 pt-1">
                      <span class="text-gray-400 dark:text-gray-500">总评：</span>{{ t.review_comment }}
                    </p>
                  </div>
                </div>
              </template>
              <p v-else class="py-3 text-xs text-gray-400 dark:text-gray-500">该月无任务记录</p>
            </div>
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
const current = ref<any>(null)
const history = ref<any[]>([])
const expandedItems = ref<Set<string>>(new Set())
const commentText = ref<Record<string, string>>({})
const updatingStatus = ref<Record<string, boolean>>({})
const submittingComment = ref<Record<string, boolean>>({})
const ackNote = ref<Record<string, string>>({})
const ackSubmitting = ref<Record<string, boolean>>({})

// 过往月份懒加载状态
const historyOpen = ref<Set<string>>(new Set())
const historyLoading = ref<Set<string>>(new Set())
const historyDetails = ref<Record<string, any>>({})

const startModalOpen = ref(false)
const startItem = ref<any>(null)
const startPlan = ref('')
const startEta = ref('')

const submitModalOpen = ref(false)
const submitItem = ref<any>(null)
const submitOutcome = ref('')
const submitReflection = ref('')
const submitSelfScores = ref<Record<string, number>>({})

const currentPeriod = new Date().toISOString().slice(0, 7)

async function fetchPlan() {
  loading.value = true
  try {
    const res = await api<any>('/api/kpi/plans/me/')
    current.value = res.current
    history.value = res.history || []
    // 任务列表默认全部展开
    expandedItems.value = new Set((res.current?.action_items || []).map((i: any) => i.id))
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function toggleExpand(itemId: string) {
  if (expandedItems.value.has(itemId)) expandedItems.value.delete(itemId)
  else expandedItems.value.add(itemId)
}

async function toggleHistory(period: string) {
  if (historyOpen.value.has(period)) {
    historyOpen.value.delete(period)
    return
  }
  historyOpen.value.add(period)
  if (historyDetails.value[period]) return
  historyLoading.value.add(period)
  try {
    const res = await api<any>(`/api/kpi/plans/me/?period=${period}`)
    historyDetails.value[period] = res.plan || { action_items: [] }
  } catch {
    historyDetails.value[period] = { action_items: [] }
  } finally {
    historyLoading.value.delete(period)
  }
}

async function updateStatus(itemId: string, newStatus: string) {
  updatingStatus.value[itemId] = true
  try {
    await api(`/api/kpi/action-items/${itemId}/status/`, {
      method: 'POST',
      body: { status: newStatus },
    })
    toast.add({ title: '状态已更新', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '更新失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[itemId] = false
  }
}

function openStart(item: any) {
  startItem.value = item
  startPlan.value = ''
  startEta.value = item.due_date || ''
  startModalOpen.value = true
}

async function confirmStart() {
  const item = startItem.value
  if (!item) return
  if (!startPlan.value.trim()) {
    toast.add({ title: '请填写「我打算怎么做」', color: 'warning' })
    return
  }
  if (!startEta.value) {
    toast.add({ title: '请填写预计完成日期', color: 'warning' })
    return
  }
  updatingStatus.value[item.id] = true
  try {
    await api(`/api/kpi/action-items/${item.id}/status/`, {
      method: 'POST',
      body: { status: 'in_progress', start_plan: startPlan.value.trim(), self_eta: startEta.value },
    })
    startModalOpen.value = false
    toast.add({ title: '已开始执行', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '操作失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[item.id] = false
  }
}

function openSubmit(item: any) {
  submitItem.value = item
  submitOutcome.value = ''
  submitReflection.value = ''
  submitSelfScores.value = {}
  submitModalOpen.value = true
}

async function confirmSubmit() {
  const item = submitItem.value
  if (!item) return
  if (!submitReflection.value.trim()) {
    toast.add({ title: '请填写「我的思考与判断」', color: 'warning' })
    return
  }
  const dims = item.review_dimensions || []
  if (dims.length && dims.some((d: any) => !submitSelfScores.value[d.key])) {
    toast.add({ title: '请对每个维度完成自评', color: 'warning' })
    return
  }
  updatingStatus.value[item.id] = true
  try {
    await api(`/api/kpi/action-items/${item.id}/status/`, {
      method: 'POST',
      body: {
        status: 'submitted',
        self_assessment: submitReflection.value.trim(),
        self_scores: submitSelfScores.value,
        note: submitOutcome.value.trim(),
      },
    })
    submitModalOpen.value = false
    toast.add({ title: '已提交', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '提交失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    updatingStatus.value[item.id] = false
  }
}

async function acknowledge(itemId: string) {
  const note = ackNote.value[itemId]?.trim()
  if (!note) return
  ackSubmitting.value[itemId] = true
  try {
    await api(`/api/kpi/action-items/${itemId}/acknowledge/`, {
      method: 'POST',
      body: { improve_note: note },
    })
    toast.add({ title: '已确认', color: 'success' })
    await fetchPlan()
  } catch (e: any) {
    toast.add({ title: '提交失败', description: e?.data?.detail || '', color: 'error' })
  } finally {
    ackSubmitting.value[itemId] = false
  }
}

async function addComment(itemId: string) {
  const content = commentText.value[itemId]?.trim()
  if (!content) return
  submittingComment.value[itemId] = true
  try {
    await api(`/api/kpi/action-items/${itemId}/comments/`, {
      method: 'POST',
      body: { content },
    })
    commentText.value[itemId] = ''
    toast.add({ title: '反馈已添加', color: 'success' })
    await fetchPlan()
  } catch {
    toast.add({ title: '发送失败', color: 'error' })
  } finally {
    submittingComment.value[itemId] = false
  }
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function priorityDot(priority: string) {
  if (priority === 'high') return 'bg-red-500'
  if (priority === 'medium') return 'bg-amber-500'
  return 'bg-gray-300 dark:bg-gray-600'
}

function statusColor(status: string): any {
  switch (status) {
    case 'in_progress': return 'info'
    case 'submitted': return 'warning'
    case 'verified': return 'success'
    case 'not_achieved': return 'error'
    default: return 'neutral'
  }
}

function statusLabel(status: string) {
  switch (status) {
    case 'pending': return '待开始'
    case 'in_progress': return '进行中'
    case 'submitted': return '已提交'
    case 'verified': return '已验收'
    case 'not_achieved': return '未达成'
    default: return status
  }
}

function isOverdue(item: any): boolean {
  if (!item.due_date || ['verified', 'not_achieved'].includes(item.status)) return false
  const t = new Date()
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
  return item.due_date < today
}

function hasReview(item: any): boolean {
  return item.scores && Object.keys(item.scores).length > 0 || !!item.review_comment
}

const actionItems = computed(() => current.value?.action_items || [])
const doneCount = computed(() => actionItems.value.filter((i: any) => i.status === 'verified').length)
const overdueCount = computed(() => actionItems.value.filter((i: any) => isOverdue(i)).length)

function statusCount(s: string) {
  return actionItems.value.filter((i: any) => i.status === s).length
}

// 状态筛选
const filterStatus = ref<string | null>(null)
const filters = computed(() => [
  { value: null, label: '全部', count: actionItems.value.length, color: 'text-gray-900 dark:text-gray-100' },
  { value: 'in_progress', label: '进行中', count: statusCount('in_progress'), color: 'text-blue-600 dark:text-blue-400' },
  { value: 'submitted', label: '待验收', count: statusCount('submitted'), color: 'text-amber-600 dark:text-amber-400' },
  { value: 'verified', label: '已达成', count: doneCount.value, color: 'text-emerald-600 dark:text-emerald-400' },
  { value: 'not_achieved', label: '未达成', count: statusCount('not_achieved'), color: 'text-red-600 dark:text-red-400' },
])
const filteredItems = computed(() =>
  filterStatus.value ? actionItems.value.filter((i: any) => i.status === filterStatus.value) : actionItems.value,
)
function toggleFilter(value: string | null) {
  filterStatus.value = filterStatus.value === value ? null : value
}
const progressPct = computed(() =>
  actionItems.value.length > 0 ? (doneCount.value / actionItems.value.length) * 100 : 0,
)

onMounted(fetchPlan)
</script>
