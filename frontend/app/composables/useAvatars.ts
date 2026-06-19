interface AvatarInfo {
  id: string
  label: string
}

interface AvatarGroup {
  id: string
  label: string
  avatars: AvatarInfo[]
}

// 内置头像分组:不同风格分开展示
const avatarGroups: AvatarGroup[] = [
  {
    id: 'geek',
    label: '极客风格',
    avatars: [
      { id: 'terminal-hacker', label: '终端黑客' },
      { id: 'robot', label: '机器人' },
      { id: 'bug-monster', label: 'Bug 怪兽' },
      { id: 'code-cat', label: '代码猫' },
      { id: 'cpu-brain', label: 'CPU 大脑' },
      { id: 'wifi-wizard', label: 'WiFi 巫师' },
      { id: 'binary-ghost', label: '二进制幽灵' },
      { id: 'docker-whale', label: 'Docker 鲸' },
      { id: 'git-octopus', label: 'Git 章鱼' },
      { id: 'code-ninja', label: '代码忍者' },
      { id: 'keyboard-warrior', label: '键盘战士' },
      { id: 'stack-overflow', label: '栈溢出' },
      { id: '404-alien', label: '404 外星人' },
      { id: 'firewall-guard', label: '防火墙守卫' },
      { id: 'one-up-mushroom', label: '1-UP 蘑菇' },
      { id: 'recursion-owl', label: '递归猫头鹰' },
      { id: 'rubber-duck', label: '小黄鸭调试' },
      { id: 'infinite-coffee', label: '无限咖啡' },
      { id: 'sudo-penguin', label: 'Sudo 企鹅' },
      { id: 'null-pointer', label: '空指针' },
    ],
  },
  {
    id: 'cartoon',
    label: '卡通插画',
    avatars: [
      { id: 'fox', label: '狐狸' },
      { id: 'bear', label: '棕熊' },
      { id: 'bear-2', label: '小熊' },
      { id: 'lion', label: '狮子' },
      { id: 'crocodile', label: '鳄鱼' },
      { id: 'giraffe', label: '长颈鹿' },
      { id: 'squirrel', label: '松鼠' },
      { id: 'wild-boar', label: '野猪' },
      { id: 'cow', label: '奶牛' },
      { id: 'bee', label: '蜜蜂' },
      { id: 'man', label: '男士' },
      { id: 'man-2', label: '男士 2' },
      { id: 'man-3', label: '男士 3' },
      { id: 'woman', label: '女士' },
      { id: 'woman-2', label: '女士 2' },
      { id: 'woman-3', label: '女士 3' },
      { id: 'planet-earth', label: '地球' },
      { id: 'leaf', label: '叶子' },
      { id: 'plant-pot', label: '盆栽' },
      { id: 'eco-friendly', label: '环保' },
      { id: 'laptop', label: '笔记本' },
      { id: 'online-training', label: '在线学习' },
      { id: 'listening', label: '听音乐' },
      { id: 'shovel', label: '铲子' },
      { id: 'ninja', label: '忍者' },
    ],
  },
]

// 扁平列表:供随机选取、按 id 查标签等场景使用
const avatarList: AvatarInfo[] = avatarGroups.flatMap(g => g.avatars)

// 内置头像同时支持 svg(极客组)与 png(卡通组,放在 flaticon 子目录)
const avatarModules = import.meta.glob('~/assets/images/avatars/**/*.{svg,png}', { eager: true, import: 'default' })

function isUploadedAvatar(id: string): boolean {
  // 上传头像存的是 URL(MinIO 公网地址或 /uploads 代理路径),内置头像存的是 id
  return /^https?:\/\//.test(id) || id.startsWith('/')
}

function resolveAvatarUrl(id: string): string {
  if (!id) return ''
  if (isUploadedAvatar(id)) return id
  const key = Object.keys(avatarModules).find(k => k.includes(`/${id}.svg`) || k.includes(`/${id}.png`))
  return key ? (avatarModules[key] as string) : ''
}

function randomAvatarId(): string {
  const item = avatarList[Math.floor(Math.random() * avatarList.length)]
  return item ? item.id : avatarList[0]!.id
}

export function useAvatars() {
  return { avatarGroups, avatarList, resolveAvatarUrl, randomAvatarId, isUploadedAvatar }
}
