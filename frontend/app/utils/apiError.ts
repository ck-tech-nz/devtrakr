// API 错误归类与友好提示。
// 后端重启/尚未就绪时,反向代理会返回 502/503/504;后端完全不可达时,
// fetch 直接抛网络错误(无 response,状态视作 0)。这些都属于"服务暂时不可用",
// 不应被当成业务错误(如登录的"用户名或密码错误")展示给用户。

const GATEWAY_STATUSES = new Set([502, 503, 504])

export const SERVICE_BUSY_MESSAGE = '系统正忙，请稍候再试'

/** 从 ofetch / $fetch 抛出的错误中取 HTTP 状态码,取不到则为 0。 */
export function getErrorStatus(e: any): number {
  return e?.response?.status ?? e?.statusCode ?? e?.status ?? 0
}

/** 网关错误(502/503/504)或无响应(0):后端尚未就绪或网络中断。 */
export function isServiceUnavailable(e: any): boolean {
  const status = getErrorStatus(e)
  return status === 0 || GATEWAY_STATUSES.has(status)
}

/**
 * 把错误转成可展示的中文提示。
 * 服务不可用 → "系统正忙,请稍候再试";否则取后端返回的 detail/字段错误,
 * 最后回退到 fallback。
 */
export function apiErrorMessage(e: any, fallback = '操作失败，请稍后重试'): string {
  if (isServiceUnavailable(e)) return SERVICE_BUSY_MESSAGE
  const data = e?.data || e?.response?._data
  if (data && typeof data === 'object') {
    const msgs = Object.values(data).flat().filter(Boolean).join('; ')
    if (msgs) return msgs
  }
  return e?.message || fallback
}
