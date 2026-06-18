interface AvatarInfo {
  id: string
  label: string
}

const avatarList: AvatarInfo[] = [
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
]

const avatarModules = import.meta.glob('~/assets/images/avatars/*.svg', { eager: true, import: 'default' })

function isUploadedAvatar(id: string): boolean {
  // 上传头像存的是 URL(MinIO 公网地址或 /uploads 代理路径),内置头像存的是 id
  return /^https?:\/\//.test(id) || id.startsWith('/')
}

function resolveAvatarUrl(id: string): string {
  if (!id) return ''
  if (isUploadedAvatar(id)) return id
  const key = Object.keys(avatarModules).find(k => k.includes(`/${id}.svg`))
  return key ? (avatarModules[key] as string) : ''
}

function randomAvatarId(): string {
  const item = avatarList[Math.floor(Math.random() * avatarList.length)]
  return item ? item.id : avatarList[0]!.id
}

export function useAvatars() {
  return { avatarList, resolveAvatarUrl, randomAvatarId, isUploadedAvatar }
}
