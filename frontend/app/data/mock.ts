// ===== Users =====
export const users = [
  { id: 'u1', name: '张三', email: 'zhangsan@company.com', github_id: 'zhangsan-dev', role: '管理员', avatar: '' },
  { id: 'u2', name: '李四', email: 'lisi@company.com', github_id: 'lisi-dev', role: '开发者', avatar: '' },
  { id: 'u3', name: '王五', email: 'wangwu@company.com', github_id: 'wangwu-dev', role: '开发者', avatar: '' },
  { id: 'u4', name: '赵六', email: 'zhaoliu@company.com', github_id: 'zhaoliu-dev', role: '开发者', avatar: '' },
  { id: 'u5', name: '孙七', email: 'sunqi@company.com', github_id: 'sunqi-dev', role: '测试', avatar: '' },
  { id: 'u6', name: '周八', email: 'zhouba@company.com', github_id: 'zhouba-dev', role: '开发者', avatar: '' },
  { id: 'u7', name: '吴九', email: 'wujiu@company.com', github_id: 'wujiu-dev', role: '前端开发', avatar: '' },
  { id: 'u8', name: '郑十', email: 'zhengshi@company.com', github_id: 'zhengshi-dev', role: '后端开发', avatar: '' },
  { id: 'u9', name: '陈明', email: 'chenming@company.com', github_id: 'chenming-dev', role: '开发者', avatar: '' },
  { id: 'u10', name: '林芳', email: 'linfang@company.com', github_id: 'linfang-dev', role: '产品经理', avatar: '' },
]

// ===== Projects =====
export const projects = [
  {
    id: 'p1',
    name: '贷后智能体平台',
    description: '基于 AI 的贷后管理系统，包含智能外呼、策略引擎等模块',
    status: '进行中',
    remark: '当前重点推进 AI 外呼模块，预计 4 月初完成核心功能联调',
    estimated_completion: '2026-04-30T00:00:00Z',
    actual_hours: 1280,
    created_at: '2026-01-15T09:00:00Z',
    updated_at: '2026-03-20T10:00:00Z',
    linked_repos: ['r1'],
    members: [
      { user_id: 'u1', role: 'owner' },
      { user_id: 'u2', role: 'admin' },
      { user_id: 'u3', role: 'member' },
      { user_id: 'u4', role: 'member' },
      { user_id: 'u5', role: 'member' },
      { user_id: 'u7', role: 'member' },
      { user_id: 'u8', role: 'member' },
    ],
  },
  {
    id: 'p2',
    name: 'DevTrakr 项目管理工具',
    description: '内部开发团队使用的项目管理和问题追踪工具',
    status: '进行中',
    remark: '第一版基本完成，后续迭代增加 GitHub 集成和 AI 分析功能',
    estimated_completion: '2026-05-15T00:00:00Z',
    actual_hours: 420,
    created_at: '2026-02-01T09:00:00Z',
    updated_at: '2026-03-19T14:00:00Z',
    linked_repos: ['r2'],
    members: [
      { user_id: 'u1', role: 'owner' },
      { user_id: 'u7', role: 'admin' },
      { user_id: 'u9', role: 'member' },
      { user_id: 'u10', role: 'member' },
    ],
  },
  {
    id: 'p3',
    name: '数据分析平台 v2',
    description: '数据可视化和报表系统重构',
    status: '已完成',
    remark: '已交付上线，运行稳定',
    estimated_completion: '2026-02-28T00:00:00Z',
    actual_hours: 960,
    created_at: '2025-09-01T09:00:00Z',
    updated_at: '2026-02-28T18:00:00Z',
    linked_repos: ['r1', 'r2'],
    members: [
      { user_id: 'u2', role: 'owner' },
      { user_id: 'u6', role: 'member' },
      { user_id: 'u8', role: 'member' },
    ],
  },
]

// ===== Labels =====
export const labelOptions = ['前端', '后端', 'Bug', '优化', '需求', '文档', 'CI/CD', '安全', '性能', 'UI/UX']

// ===== Issues (50+) =====
const issueRemarks = [
  '需要与外呼服务团队联调', '阻塞策略模块上线', '前端已修复，待后端配合',
  '已联系模型团队排查', '需要更新音色配置文档', '产品确认优化方向',
  '已上线，观察效果', '依赖策略模块完成', '对接文书系统团队',
  '需要电话线路支持', '', '与 ISS-001 可能相关',
  '等待产品验收', '设计稿已确认', '', '已修复，待回归测试',
  '参考现有系统实现', '参数需要持续调优', '需要运维协助查看日志',
  '', '准确率已达到 95%+', 'API 隔离方案已评审通过',
  '架构升级风险较高，需灰度发布', '知识库持续补充中', '方案已评审',
  '', '已合并到 CI 流水线', '下次上线前完成', '安全审计重点关注', '需要压测验证',
]

const issueTemplates = [
  { title: '执行完成后偶发未外呼', labels: ['Bug', '后端'], cause: '批次外呼任务异步执行时序问题', solution: '增加任务状态校验和重试机制' },
  { title: '外呼内容与策略选择无挂钩', labels: ['Bug', '后端'], cause: '话术与策略关联逻辑缺失', solution: '增加策略-话术映射配置' },
  { title: '上传案件表格信息无关', labels: ['Bug', '前端'], cause: '仅姓名有关联，其他字段未映射', solution: '完善字段映射逻辑' },
  { title: 'AI 均通时有概率叫错名字', labels: ['Bug', '后端', '性能'], cause: '模型调用时的参数传递问题', solution: '修复参数传递和名称校验' },
  { title: '音色为默认音色（非录制音色）', labels: ['Bug', '后端'], cause: '调用API时的默认音色非克隆音', solution: '配置默认音色为克隆音色ID' },
  { title: 'AI 第一句不像真人', labels: ['优化', '后端'], cause: '开场白内容过长，缩短后效果有提升', solution: '优化开场白生成策略' },
  { title: '闪信功能：不同单位及单账号可配置', labels: ['需求', '后端'], cause: '', solution: '已实现闪信功能，支持多单位配置' },
  { title: '短信模板配置与内容配置完善', labels: ['需求', '前端', '后端'], cause: '', solution: '等待AI策略功能完成后集成' },
  { title: '文书生成→转链接→写入短信变量', labels: ['需求', '后端'], cause: '', solution: '引入已开发的功能模块' },
  { title: '呼入语音：需考虑呼入案件对应', labels: ['需求', '后端'], cause: '', solution: '实现用户回拨和呼入功能，根据用户号码匹配' },
  { title: '策略执行间隔时间、执行时间完善', labels: ['Bug', '后端'], cause: '定时任务间隔不精确', solution: '优化调度器时间精度' },
  { title: '批次完成后电话触发时间过久', labels: ['Bug', '后端'], cause: '可能与偶发未外呼相关', solution: '排查任务队列延迟' },
  { title: '用户仪表盘及单次策略作业数据完善', labels: ['需求', '前端'], cause: '', solution: '已完成等待验收' },
  { title: '前端交互设计优化', labels: ['优化', 'UI/UX', '前端'], cause: '', solution: '已转交设计评审' },
  { title: '策略匹配条件优化', labels: ['优化', '后端'], cause: '条件匹配不够精细', solution: '已优化，策略匹配更精确' },
  { title: '多个案件编号重量，导致案件详情页显示相同', labels: ['Bug', '前端'], cause: '没有去重机制', solution: '已优化去重逻辑' },
  { title: '缺少角色管理页面', labels: ['需求', '前端'], cause: '', solution: '参考外呼智能体平台实现' },
  { title: '打断机制太敏感', labels: ['Bug', '后端'], cause: '环境音/公告导致频繁打断', solution: '打断参数设置较低，已优化完成' },
  { title: '延迟不正常（偶发约2s回复）', labels: ['Bug', '后端', '性能'], cause: '需要排查请求日志', solution: '排查中' },
  { title: '系统整体功能不完整，页面功能偏少', labels: ['需求', '前端'], cause: '需要增加接口或功能', solution: '已将前端分离出来方便落实需求' },
  { title: '意图识别不准', labels: ['Bug', '后端'], cause: '意图分析识别模式不够精确', solution: '已引入LLM实时分析，准确率大幅提升' },
  { title: 'API调用外呼接口时信息冲突', labels: ['Bug', '后端'], cause: '同时内外部调用API', solution: '实现用户信息隔离，API独立两套流程' },
  { title: '实时外呼通话时无法快速调用RAG', labels: ['优化', '后端', '性能'], cause: '语音模型不支持 Function Calling', solution: '升级为三通道注入架构' },
  { title: 'SKILL层的话术知识库内容不足', labels: ['优化', '后端'], cause: '专业领域知识覆盖不足', solution: '添加金融贷后领域14个术语库和26部法律法规' },
  { title: '贷后智能体策略智能化生成', labels: ['需求', '后端'], cause: '', solution: '已完成方案设计和开发' },
  { title: '登录页面样式调整', labels: ['优化', 'UI/UX', '前端'], cause: '', solution: '对齐设计稿' },
  { title: 'Docker 部署脚本优化', labels: ['优化', 'CI/CD'], cause: '镜像体积过大', solution: '使用多阶段构建减小镜像' },
  { title: '数据库索引缺失导致查询慢', labels: ['Bug', '后端', '性能'], cause: '高频查询字段未建索引', solution: '添加复合索引' },
  { title: '用户权限校验不完整', labels: ['Bug', '安全', '后端'], cause: '部分API缺少权限中间件', solution: '统一添加权限装饰器' },
  { title: 'WebSocket 连接偶发断开', labels: ['Bug', '后端'], cause: '心跳机制不完善', solution: '增加自动重连和心跳检测' },
]

const priorities = ['P0', 'P1', 'P2', 'P3'] as const
const statuses = ['待分配', '待确认', '进行中', '已解决', '已关闭'] as const
const assignees = ['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7', 'u8', 'u9', 'u10']
const reporters = ['u1', 'u2', 'u5', 'u10']

// Seeded PRNG for deterministic mock data across page loads
let _seed = 42
function seededRandom(): number {
  _seed = (_seed * 16807 + 0) % 2147483647
  return (_seed - 1) / 2147483646
}

function randomFrom<T>(arr: readonly T[]): T {
  return arr[Math.floor(seededRandom() * arr.length)]
}

function generateIssues() {
  const result = []
  for (let i = 0; i < issueTemplates.length; i++) {
    const t = issueTemplates[i]
    const status = randomFrom(statuses)
    const priority = randomFrom(priorities)
    const assignee = randomFrom(assignees)
    const reporter = randomFrom(reporters)
    const projectId = i < 20 ? 'p1' : i < 25 ? 'p2' : randomFrom(['p1', 'p2', 'p3'])
    const createdDate = new Date(2026, 2, Math.floor(seededRandom() * 20) + 1)
    const resolved = status === '已解决' || status === '已关闭'
    const resolvedDate = resolved ? new Date(createdDate.getTime() + seededRandom() * 7 * 86400000) : null
    const branchMerged = resolved && seededRandom() > 0.3
    const branchCreated = resolved || status === '进行中' ? new Date(createdDate.getTime() + seededRandom() * 86400000) : null

    const estimatedDays = Math.floor(seededRandom() * 10) + 1
    const estimatedDate = new Date(createdDate.getTime() + estimatedDays * 86400000)
    const actualHours = resolved ? Math.round((resolvedDate!.getTime() - createdDate.getTime()) / 3600000) : (status === '进行中' ? Math.floor(seededRandom() * 40) + 2 : null)

    result.push({
      id: `ISS-${String(i + 1).padStart(3, '0')}`,
      project_id: projectId,
      title: t.title,
      description: `${t.title}的详细描述。该问题影响了系统的正常运行，需要尽快处理。`,
      priority,
      status,
      labels: t.labels,
      reporter,
      assignee,
      remark: issueRemarks[i] || '',
      estimated_completion: estimatedDate.toISOString(),
      actual_hours: actualHours,
      cause: t.cause,
      solution: t.solution,
      created_at: createdDate.toISOString(),
      resolved_at: resolvedDate?.toISOString() || null,
      resolution_hours: resolvedDate ? Math.round((resolvedDate.getTime() - createdDate.getTime()) / 3600000) : null,
      branch_name: branchCreated ? `fix/iss-${i + 1}-${t.title.slice(0, 10).replace(/\s/g, '-')}` : null,
      branch_created_at: branchCreated?.toISOString() || null,
      branch_merged_at: branchMerged ? new Date(branchCreated!.getTime() + seededRandom() * 5 * 86400000).toISOString() : null,
      linked_commits: resolved ? [`abc${String(i).padStart(4, '0')}`, `def${String(i).padStart(4, '0')}`] : [],
      linked_prs: resolved ? [100 + i] : [],
      ai_analysis: seededRandom() > 0.3 ? {
        suggested_priority: randomFrom(priorities),
        suggested_labels: t.labels.slice(0, 2),
        resolution_hints: [
          `建议检查${t.labels[0]}相关模块`,
          '可以参考类似问题的解决方案',
          '建议进行回归测试确认修复效果',
        ],
        related_files: [
          `src/${t.labels.includes('前端') ? 'components' : 'services'}/${t.title.slice(0, 6)}.${t.labels.includes('前端') ? 'vue' : 'py'}`,
          `tests/test_${t.title.slice(0, 6)}.py`,
        ],
      } : null,
    })
  }
  for (let i = issueTemplates.length; i < 55; i++) {
    const status = randomFrom(statuses)
    const resolved = status === '已解决' || status === '已关闭'
    const createdDate = new Date(2026, 2, Math.floor(seededRandom() * 20) + 1)
    const resolvedDate = resolved ? new Date(createdDate.getTime() + seededRandom() * 7 * 86400000) : null
    const estDays = Math.floor(seededRandom() * 10) + 1
    const estDate = new Date(createdDate.getTime() + estDays * 86400000)
    const actHours = resolved ? Math.round((resolvedDate!.getTime() - createdDate.getTime()) / 3600000) : (status === '进行中' ? Math.floor(seededRandom() * 40) + 2 : null)
    result.push({
      id: `ISS-${String(i + 1).padStart(3, '0')}`,
      project_id: randomFrom(['p1', 'p2', 'p3']),
      title: `系统优化任务 #${i + 1}`,
      description: `常规优化任务，需要处理相关模块的性能和稳定性问题。`,
      priority: randomFrom(priorities),
      status,
      labels: [randomFrom(labelOptions), randomFrom(labelOptions)],
      reporter: randomFrom(reporters),
      assignee: randomFrom(assignees),
      remark: '',
      estimated_completion: estDate.toISOString(),
      actual_hours: actHours,
      cause: '',
      solution: resolved ? '已修复' : '',
      created_at: createdDate.toISOString(),
      resolved_at: resolvedDate?.toISOString() || null,
      resolution_hours: resolvedDate ? Math.round((resolvedDate.getTime() - createdDate.getTime()) / 3600000) : null,
      branch_name: null,
      branch_created_at: null,
      branch_merged_at: null,
      linked_commits: [],
      linked_prs: [],
      ai_analysis: null,
    })
  }
  return result
}

export const issues = generateIssues()

// ===== GitHub Repos =====
export const repos = [
  {
    id: 'r1',
    name: 'postloan-backend',
    full_name: 'matrix/postloan-backend',
    url: 'https://github.com/matrix/postloan-backend',
    description: '贷后智能体平台后端服务',
    default_branch: 'main',
    language: 'Python',
    stars: 12,
    connected_at: '2026-01-20T10:00:00Z',
    status: '在线',
    recent_commits: [
      { sha: 'a1b2c3d', message: 'feat: add strategy execution engine', author: 'zhangsan-dev', date: '2026-03-20T09:30:00Z' },
      { sha: 'e4f5g6h', message: 'fix: resolve call record duplication', author: 'lisi-dev', date: '2026-03-19T16:45:00Z' },
      { sha: 'i7j8k9l', message: 'refactor: optimize database queries', author: 'wangwu-dev', date: '2026-03-19T14:20:00Z' },
      { sha: 'm0n1o2p', message: 'docs: update API documentation', author: 'zhangsan-dev', date: '2026-03-18T11:00:00Z' },
      { sha: 'q3r4s5t', message: 'fix: handle edge case in SMS template', author: 'zhaoliu-dev', date: '2026-03-18T09:15:00Z' },
      { sha: 'u6v7w8x', message: 'feat: add RAG knowledge base integration', author: 'lisi-dev', date: '2026-03-17T15:30:00Z' },
      { sha: 'y9z0a1b', message: 'test: add unit tests for call module', author: 'sunqi-dev', date: '2026-03-17T10:00:00Z' },
      { sha: 'c2d3e4f', message: 'chore: upgrade dependencies', author: 'wangwu-dev', date: '2026-03-16T14:00:00Z' },
    ],
    open_prs: [
      { number: 142, title: 'feat: implement voice cloning API', author: 'lisi-dev', status: 'open', created_at: '2026-03-20T08:00:00Z' },
      { number: 140, title: 'fix: resolve concurrent call conflict', author: 'wangwu-dev', status: 'open', created_at: '2026-03-19T10:00:00Z' },
      { number: 138, title: 'refactor: split strategy module', author: 'zhangsan-dev', status: 'open', created_at: '2026-03-18T09:00:00Z' },
    ],
    open_issues: [
      { number: 89, title: 'Memory leak in WebSocket handler', author: 'sunqi-dev', status: 'open', labels: ['bug', 'priority:high'], created_at: '2026-03-19T11:00:00Z' },
      { number: 87, title: 'Add rate limiting for external APIs', author: 'zhangsan-dev', status: 'open', labels: ['enhancement'], created_at: '2026-03-18T14:00:00Z' },
    ],
  },
  {
    id: 'r2',
    name: 'postloan-frontend',
    full_name: 'matrix/postloan-frontend',
    url: 'https://github.com/matrix/postloan-frontend',
    description: '贷后智能体平台前端应用',
    default_branch: 'main',
    language: 'TypeScript',
    stars: 5,
    connected_at: '2026-01-20T10:05:00Z',
    status: '在线',
    recent_commits: [
      { sha: 'f1g2h3i', message: 'feat: add theme-pm scaffold', author: 'wujiu-dev', date: '2026-03-20T10:00:00Z' },
      { sha: 'j4k5l6m', message: 'fix: resolve runtime errors across themes', author: 'wujiu-dev', date: '2026-03-19T12:00:00Z' },
      { sha: 'n7o8p9q', message: 'feat: add single-port showcase server', author: 'chenming-dev', date: '2026-03-18T16:00:00Z' },
      { sha: 'r0s1t2u', message: 'feat: add Theme C complete', author: 'wujiu-dev', date: '2026-03-17T11:00:00Z' },
      { sha: 'v3w4x5y', message: 'feat: add Theme B complete', author: 'chenming-dev', date: '2026-03-16T15:00:00Z' },
    ],
    open_prs: [
      { number: 28, title: 'feat: implement theme-pm project management tool', author: 'wujiu-dev', status: 'open', created_at: '2026-03-20T09:00:00Z' },
    ],
    open_issues: [
      { number: 15, title: 'Mobile responsive issues on dashboard', author: 'linfang-dev', status: 'open', labels: ['bug', 'UI'], created_at: '2026-03-19T09:00:00Z' },
    ],
  },
]

// ===== Dashboard Stats =====
export const dashboardStats = {
  total_issues: issues.length,
  pending_issues: issues.filter(i => i.status === '待分配').length,
  in_progress_issues: issues.filter(i => i.status === '进行中').length,
  resolved_this_week: issues.filter(i => {
    if (!i.resolved_at) return false
    const resolved = new Date(i.resolved_at)
    const weekAgo = new Date(2026, 2, 14)
    return resolved >= weekAgo
  }).length,
}

// ===== 30-day Issue Trends =====
export const dailyTrends = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(2026, 2, 20)
  d.setDate(d.getDate() - 29 + i)
  return {
    date: d.toISOString().slice(0, 10),
    created: Math.floor(seededRandom() * 6 + 1),
    resolved: Math.floor(seededRandom() * 5 + 1),
  }
})

// ===== Priority Distribution =====
export const priorityDistribution = [
  { name: 'P0', value: issues.filter(i => i.priority === 'P0').length },
  { name: 'P1', value: issues.filter(i => i.priority === 'P1').length },
  { name: 'P2', value: issues.filter(i => i.priority === 'P2').length },
  { name: 'P3', value: issues.filter(i => i.priority === 'P3').length },
]

// ===== Developer Stats =====
export const developerStats = users
  .filter(u => ['开发者', '前端开发', '后端开发'].includes(u.role))
  .map(u => {
    const userIssues = issues.filter(i => i.assignee === u.id)
    const resolved = userIssues.filter(i => i.status === '已解决' || i.status === '已关闭')
    const withBranch = resolved.filter(i => i.branch_merged_at && i.branch_created_at)
    const avgHours = withBranch.length > 0
      ? Math.round(withBranch.reduce((sum, i) => sum + (new Date(i.branch_merged_at!).getTime() - new Date(i.branch_created_at!).getTime()) / 3600000, 0) / withBranch.length)
      : null
    return {
      user_id: u.id,
      user_name: u.name,
      project_id: 'p1',
      avg_resolution_hours: avgHours,
      monthly_resolved_count: resolved.length,
      priority_distribution: {
        P0: resolved.filter(i => i.priority === 'P0').length,
        P1: resolved.filter(i => i.priority === 'P1').length,
        P2: resolved.filter(i => i.priority === 'P2').length,
        P3: resolved.filter(i => i.priority === 'P3').length,
      },
      resolution_trend: [
        { month: '2026-01', count: Math.floor(seededRandom() * 8 + 2) },
        { month: '2026-02', count: Math.floor(seededRandom() * 10 + 3) },
        { month: '2026-03', count: resolved.length },
      ],
    }
  })

// ===== AI Insights =====
export const aiInsights = {
  project_id: 'p1',
  generated_at: '2026-03-20T08:00:00Z',
  team_efficiency: {
    avg_resolution_trend: [
      { month: '2026-01', hours: 52 },
      { month: '2026-02', hours: 45 },
      { month: '2026-03', hours: 38 },
    ],
    per_person_output: developerStats.map(d => ({
      name: d.user_name,
      count: d.monthly_resolved_count,
    })),
  },
  bottlenecks: [
    { type: 'assignee' as const, name: '李四', pending_count: 8 },
    { type: 'assignee' as const, name: '王五', pending_count: 6 },
    { type: 'label' as const, name: '后端', pending_count: 15 },
    { type: 'label' as const, name: '性能', pending_count: 7 },
  ],
  trend_alerts: [
    { message: 'P0 问题本周新增 3 个，较上周增长 200%', severity: 'critical' as const, metric: 'P0 新增', change_pct: 200 },
    { message: '后端 Bug 积压量持续增加，建议增加人手', severity: 'warning' as const, metric: '后端积压', change_pct: 45 },
    { message: '平均解决时间持续下降，团队效率提升', severity: 'warning' as const, metric: '解决速度', change_pct: -15 },
  ],
  recommendations: [
    '建议将 P0 问题分配给经验丰富的开发者优先处理',
    '后端标签下积压问题较多，建议进行代码审查找出系统性问题',
    '李四当前积压 8 个问题，建议重新分配部分任务',
    '性能类问题建议集中处理，安排专项优化迭代',
  ],
}

// ===== Recent Activity =====
export const recentActivity = [
  { id: 1, icon: 'i-heroicons-plus-circle', message: '张三 创建了问题 ISS-025「贷后智能体策略智能化生成」', time: '10 分钟前' },
  { id: 2, icon: 'i-heroicons-check-circle', message: '李四 解决了问题 ISS-005「音色为默认音色」', time: '30 分钟前' },
  { id: 3, icon: 'i-heroicons-code-bracket', message: '王五 关联了 PR #142 到 ISS-010', time: '1 小时前' },
  { id: 4, icon: 'i-heroicons-arrow-path', message: '赵六 将 ISS-018「打断机制太敏感」状态改为已解决', time: '2 小时前' },
  { id: 5, icon: 'i-heroicons-cpu-chip', message: 'AI 分析完成：ISS-023「实时外呼通话调用RAG」建议优先级 P1', time: '3 小时前' },
  { id: 6, icon: 'i-heroicons-user-plus', message: '张三 将 ISS-012 分配给 孙七', time: '4 小时前' },
  { id: 7, icon: 'i-heroicons-flag', message: '林芳 将 ISS-001 优先级调整为 P0', time: '5 小时前' },
  { id: 8, icon: 'i-heroicons-code-bracket', message: '吴九 为 ISS-016 创建了分支 fix/iss-16-缺少角色管理', time: '6 小时前' },
]

// Helper: get user name by id
export function getUserName(id: string): string {
  return users.find(u => u.id === id)?.name ?? id
}
