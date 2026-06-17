export function useBackupFormat() {
  function formatSize(bytes: number | null): string {
    if (bytes == null) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function formatTime(iso: string): string {
    return new Date(iso).toLocaleString('zh-CN')
  }

  const statusMap: Record<string, { label: string; color: 'success' | 'warning' | 'error' }> = {
    running: { label: '备份中', color: 'warning' },
    success: { label: '成功', color: 'success' },
    failed: { label: '失败', color: 'error' },
  }

  return { formatSize, formatTime, statusMap }
}
