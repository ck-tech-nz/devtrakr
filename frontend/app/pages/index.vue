<template>
  <div class="w-full max-w-5xl mx-auto px-6 self-start py-10 md:py-14">
    <!-- AI Spotlight: latest feature -->
    <AiSpotlight class="mb-16 md:mb-20" />

    <div class="flex flex-col md:flex-row items-center gap-12 md:gap-16">
      <!-- Left: Branding + CTAs -->
      <div class="flex-1 flex flex-col items-start">
        <div class="flex items-center gap-3 mb-6">
          <img src="~/assets/images/logo-icon.svg" alt="DevTrakr" class="w-12 h-12" />
          <span class="text-2xl font-bold text-gray-900">DevTrakr</span>
        </div>
        <h1 class="text-3xl md:text-4xl font-bold text-gray-900 leading-tight mb-4">
          团队项目管理<br />高效协作
        </h1>
        <p class="text-gray-500 mb-8 text-base leading-relaxed">一站式项目管理平台，让团队协作更简单</p>

        <div class="space-y-3 mb-10 w-full">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-crystal-50 flex items-center justify-center flex-shrink-0">
              <UIcon name="i-heroicons-clipboard-document-list" class="w-4 h-4 text-crystal-500" />
            </div>
            <div>
              <span class="text-sm font-medium text-gray-900">Issue 追踪</span>
              <span class="text-sm text-gray-400 ml-2">创建、分配、跟踪问题</span>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-crystal-50 flex items-center justify-center flex-shrink-0">
              <UIcon name="i-heroicons-chart-bar" class="w-4 h-4 text-crystal-500" />
            </div>
            <div>
              <span class="text-sm font-medium text-gray-900">数据看板</span>
              <span class="text-sm text-gray-400 ml-2">实时统计分析</span>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-crystal-50 flex items-center justify-center flex-shrink-0">
              <UIcon name="i-heroicons-user-group" class="w-4 h-4 text-crystal-500" />
            </div>
            <div>
              <span class="text-sm font-medium text-gray-900">团队协作</span>
              <span class="text-sm text-gray-400 ml-2">权限与角色管理</span>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-crystal-50 flex items-center justify-center flex-shrink-0">
              <UIcon name="i-heroicons-code-bracket" class="w-4 h-4 text-crystal-500" />
            </div>
            <div>
              <span class="text-sm font-medium text-gray-900">仓库集成</span>
              <span class="text-sm text-gray-400 ml-2">Git 仓库关联</span>
            </div>
          </div>
        </div>

        <div class="flex gap-3">
          <UButton to="/login" size="lg" color="primary">登录</UButton>
          <UButton to="/register" size="lg" variant="outline" color="neutral">注册</UButton>
        </div>
      </div>

      <!-- Right: App Preview Mockup -->
      <div class="flex-1 hidden md:block">
        <div class="bg-white rounded-2xl shadow-xl shadow-crystal-100/50 border border-gray-100 p-5">
          <!-- Mini Kanban -->
          <div class="mb-4">
            <div class="text-xs font-semibold text-gray-700 mb-2">Issue 看板</div>
            <div class="flex gap-2">
              <div class="flex-1 bg-amber-50 rounded-lg p-2.5">
                <div class="text-[10px] font-medium text-amber-700 mb-1.5">待处理</div>
                <div class="space-y-1">
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">页面优化</div>
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">权限修复</div>
                </div>
              </div>
              <div class="flex-1 bg-blue-50 rounded-lg p-2.5">
                <div class="text-[10px] font-medium text-blue-700 mb-1.5">进行中</div>
                <div class="space-y-1">
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">API 开发</div>
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">数据迁移</div>
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">单元测试</div>
                </div>
              </div>
              <div class="flex-1 bg-emerald-50 rounded-lg p-2.5">
                <div class="text-[10px] font-medium text-emerald-700 mb-1.5">已完成</div>
                <div class="space-y-1">
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">用户认证</div>
                  <div class="bg-white rounded px-2 py-1 text-[10px] text-gray-600 shadow-sm">部署配置</div>
                </div>
              </div>
            </div>
          </div>
          <!-- Mini Trend -->
          <div>
            <div class="text-xs font-semibold text-gray-700 mb-2">趋势</div>
            <div class="h-16 bg-gradient-to-r from-crystal-50 via-crystal-100 to-crystal-200 rounded-lg flex items-end px-3 pb-2 gap-1.5">
              <div class="w-3 bg-crystal-300 rounded-t" style="height: 30%"></div>
              <div class="w-3 bg-crystal-400 rounded-t" style="height: 50%"></div>
              <div class="w-3 bg-crystal-300 rounded-t" style="height: 40%"></div>
              <div class="w-3 bg-crystal-500 rounded-t" style="height: 70%"></div>
              <div class="w-3 bg-crystal-400 rounded-t" style="height: 55%"></div>
              <div class="w-3 bg-crystal-500 rounded-t" style="height: 80%"></div>
              <div class="w-3 bg-crystal-600 rounded-t" style="height: 65%"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <p class="text-center text-xs text-gray-400 mt-12">&copy; 2026 DevTrakr 项目管理平台</p>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'auth' })

const { getToken } = useApi()

onMounted(() => {
  if (getToken()) {
    navigateTo('/app/home')
  }
})
</script>
