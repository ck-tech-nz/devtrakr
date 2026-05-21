type DialogColor = 'primary' | 'error' | 'warning' | 'success' | 'info' | 'neutral'
type DialogSize = 'md' | 'lg' | 'xl'

export type ConfirmOptions = {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  color?: DialogColor
  icon?: string
}

export type AlertOptions = {
  title?: string
  message?: string
  htmlBody?: string
  persistent?: boolean
  confirmText?: string
  color?: DialogColor
  icon?: string
  size?: DialogSize
}

type DialogState = {
  open: boolean
  mode: 'confirm' | 'alert'
  title: string
  message: string
  htmlBody: string
  persistent: boolean
  confirmText: string
  cancelText: string
  color: DialogColor
  icon: string
  size: DialogSize
  resolve: ((v: boolean) => void) | null
}

const defaultState = (): DialogState => ({
  open: false,
  mode: 'confirm',
  title: '',
  message: '',
  htmlBody: '',
  persistent: false,
  confirmText: '确认',
  cancelText: '取消',
  color: 'primary',
  icon: '',
  size: 'md',
  resolve: null,
})

export const useDialog = () => {
  const state = useState<DialogState>('app-dialog', defaultState)

  function _respond(value: boolean) {
    state.value.resolve?.(value)
    state.value = { ...defaultState() }
  }

  function confirm(opts: ConfirmOptions | string): Promise<boolean> {
    if (state.value.resolve) state.value.resolve(false)
    const o: ConfirmOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise((resolve) => {
      state.value = {
        open: true,
        mode: 'confirm',
        title: o.title || '请确认',
        message: o.message,
        htmlBody: '',
        persistent: false,
        confirmText: o.confirmText || '确认',
        cancelText: o.cancelText || '取消',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-exclamation-triangle' : ''),
        size: 'md',
        resolve,
      }
    })
  }

  function alert(opts: AlertOptions | string): Promise<void> {
    if (state.value.resolve) state.value.resolve(false)
    const o: AlertOptions = typeof opts === 'string' ? { message: opts } : opts
    return new Promise<void>((resolve) => {
      state.value = {
        open: true,
        mode: 'alert',
        title: o.title || '提示',
        message: o.message || '',
        htmlBody: o.htmlBody || '',
        persistent: o.persistent === true,
        confirmText: o.confirmText || '知道了',
        cancelText: '',
        color: o.color || 'primary',
        icon: o.icon || (o.color === 'error' ? 'i-heroicons-x-circle' : o.color === 'warning' ? 'i-heroicons-exclamation-triangle' : o.color === 'success' ? 'i-heroicons-check-circle' : 'i-heroicons-information-circle'),
        size: o.size || 'md',
        resolve: () => resolve(),
      }
    })
  }

  return { state, confirm, alert, _respond }
}
