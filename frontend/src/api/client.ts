/** 统一请求封装：拼后端地址、带上当前岗位账号、抛网络错误、给页脚留一句可读的说明。 */
import { SESSION_STORAGE_KEY } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const operatorId = localStorage.getItem(SESSION_STORAGE_KEY) ?? ''
  const headers = new Headers(init?.headers ?? { 'Content-Type': 'application/json' })
  if (operatorId) {
    headers.set('X-Operator-Id', operatorId)
  }
  return fetch(url, { ...init, headers }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
