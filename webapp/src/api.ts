import { telegramInitData } from './telegram'

export type User = { id: number; telegram_id?: number; display_name: string }
export type Group = { id: number; name: string; raw_name?: string; role?: string; owner_user_id: number; currency: string }
export type Member = { user_id: number; display_name: string; role: string; telegram_id?: number }
export type Expense = { id: number; title: string; amount: string; category?: string; paid_by_name?: string; paid_by_user_id?: number }

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  const initData = telegramInitData()
  if (initData) headers.set('X-Telegram-Init-Data', initData)
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`)
  return res.json()
}

export async function ensureUser(): Promise<User> {
  const tg = window.Telegram?.WebApp?.initDataUnsafe?.user
  if (!tg) throw new Error('Mini App must be opened inside Telegram')
  const displayName = [tg.first_name, tg.last_name].filter(Boolean).join(' ') || tg.username || String(tg.id)
  return request('/api/v1/users', { method: 'POST', body: JSON.stringify({ telegram_id: tg.id, display_name: displayName }) })
}

export const api = {
  groups: (userId: number) => request<Group[]>(`/api/v1/dashboard/users/${userId}/groups`),
  summary: (userId: number) => request<any>(`/api/v1/dashboard/users/${userId}/summary`),
  group: (id: number) => request<Group>(`/api/v1/groups/${id}`),
  members: (id: number) => request<Member[]>(`/api/v1/groups/${id}/members`),
  expenses: (id: number) => request<Expense[]>(`/api/v1/groups/${id}/expenses?limit=20`),
  expenseReport: (id: number, actor: number) => request<any>(`/api/v1/product/groups/${id}/reports/expenses?actor_user_id=${actor}`),
  debtReport: (id: number, actor: number) => request<any>(`/api/v1/product/groups/${id}/reports/debts?actor_user_id=${actor}`),
  settlementPlan: (id: number) => request<any[]>(`/api/v1/groups/${id}/settlement-plan`),
  paymentProfile: (id: number) => request<any>(`/api/v1/product/users/${id}/payment-profile`),
  createExpense: (groupId: number, payload: any) => request(`/api/v1/groups/${groupId}/expenses`, { method: 'POST', body: JSON.stringify(payload) }),
}
