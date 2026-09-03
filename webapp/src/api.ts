import { telegramInitData } from './telegram'

export type User = { id: number; telegram_id?: number; display_name: string }
export type Group = { id: number; name: string; raw_name?: string; role?: string; owner_user_id: number; currency: string }
export type Member = { user_id: number; display_name: string; role: string; telegram_id?: number }
export type Expense = { id: number; title: string; amount: string; category?: string; paid_by_name?: string; paid_by_user_id?: number }

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const isLocalhost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
export const DEMO_MODE = isLocalhost && !window.Telegram?.WebApp?.initData

const demoUser: User = { id: 1, telegram_id: 100000001, display_name: 'ساجد فلاح' }
const demoGroups: Group[] = [
  { id: 101, name: '👑 سفر شمال', raw_name: 'سفر شمال 🌴', role: 'owner', owner_user_id: 1, currency: 'IRT' },
  { id: 102, name: '👑 خانه', raw_name: 'خانه 🏠', role: 'owner', owner_user_id: 1, currency: 'IRT' },
]
const demoMembers: Record<number, Member[]> = {
  101: [
    { user_id: 1, display_name: 'ساجد', role: 'owner' },
    { user_id: 2, display_name: 'علی', role: 'member' },
    { user_id: 3, display_name: 'رضا', role: 'member' },
    { user_id: 4, display_name: 'محمد', role: 'member' },
  ],
  102: [
    { user_id: 1, display_name: 'ساجد', role: 'owner' },
    { user_id: 5, display_name: 'مریم', role: 'member' },
    { user_id: 6, display_name: 'نگار', role: 'member' },
  ],
}
const demoExpenses: Record<number, Expense[]> = {
  101: [
    { id: 1, title: 'شام رستوران', amount: '1850000', category: 'food', paid_by_user_id: 1 },
    { id: 2, title: 'تاکسی', amount: '420000', category: 'transport', paid_by_user_id: 2 },
    { id: 3, title: 'هتل', amount: '6200000', category: 'stay', paid_by_user_id: 3 },
    { id: 4, title: 'تفریحات ساحلی', amount: '1680000', category: 'entertainment', paid_by_user_id: 1 },
    { id: 5, title: 'بنزین', amount: '2650000', category: 'fuel', paid_by_user_id: 2 },
  ],
  102: [
    { id: 6, title: 'خرید هفتگی', amount: '3200000', category: 'shopping', paid_by_user_id: 1 },
    { id: 7, title: 'قبض اینترنت', amount: '650000', category: 'other', paid_by_user_id: 5 },
  ],
}

function demoExpenseReport(groupId: number) {
  const rows = demoExpenses[groupId] || []
  const byCategory = new Map<string, { amount: number; count: number }>()
  for (const row of rows) {
    const key = row.category || 'other'
    const current = byCategory.get(key) || { amount: 0, count: 0 }
    current.amount += Number(row.amount)
    current.count += 1
    byCategory.set(key, current)
  }
  return {
    total_amount: String(rows.reduce((sum, row) => sum + Number(row.amount), 0)),
    expense_count: rows.length,
    categories: [...byCategory.entries()].map(([category, value]) => ({ category, amount: String(value.amount), count: value.count })),
  }
}

function demoDebtReport(groupId: number) {
  if (groupId === 102) return { balances: [], transfers: [] }
  return {
    balances: [
      { user_id: 1, display_name: 'ساجد', balance: '2450000', status: 'creditor' },
      { user_id: 2, display_name: 'علی', balance: '-1200000', status: 'debtor' },
      { user_id: 3, display_name: 'رضا', balance: '-800000', status: 'debtor' },
      { user_id: 4, display_name: 'محمد', balance: '-450000', status: 'debtor' },
    ],
    transfers: [
      { from_user_id: 2, from_name: 'علی', to_user_id: 1, to_name: 'ساجد', amount: '1200000' },
      { from_user_id: 3, from_name: 'رضا', to_user_id: 1, to_name: 'ساجد', amount: '800000' },
      { from_user_id: 4, from_name: 'محمد', to_user_id: 1, to_name: 'ساجد', amount: '450000' },
    ],
  }
}

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
  if (DEMO_MODE) return structuredClone(demoUser)
  const tg = window.Telegram?.WebApp?.initDataUnsafe?.user
  if (!tg) throw new Error('Mini App must be opened inside Telegram')
  const displayName = [tg.first_name, tg.last_name].filter(Boolean).join(' ') || tg.username || String(tg.id)
  return request('/api/v1/users', { method: 'POST', body: JSON.stringify({ telegram_id: tg.id, display_name: displayName }) })
}

export const api = {
  groups: async (userId: number) => DEMO_MODE ? structuredClone(demoGroups) : request<Group[]>(`/api/v1/dashboard/users/${userId}/groups`),
  summary: async (userId: number) => DEMO_MODE ? ({ owned_active_groups: 2, total_memberships: 2, free_owned_group_limit: 2, remaining_free_groups: 0 }) : request<any>(`/api/v1/dashboard/users/${userId}/summary`),
  group: async (id: number) => DEMO_MODE ? structuredClone(demoGroups.find(g => g.id === id)!) : request<Group>(`/api/v1/groups/${id}`),
  members: async (id: number) => DEMO_MODE ? structuredClone(demoMembers[id] || []) : request<Member[]>(`/api/v1/groups/${id}/members`),
  expenses: async (id: number) => DEMO_MODE ? structuredClone(demoExpenses[id] || []) : request<Expense[]>(`/api/v1/groups/${id}/expenses?limit=20`),
  expenseReport: async (id: number, actor: number) => DEMO_MODE ? demoExpenseReport(id) : request<any>(`/api/v1/product/groups/${id}/reports/expenses?actor_user_id=${actor}`),
  debtReport: async (id: number, actor: number) => DEMO_MODE ? demoDebtReport(id) : request<any>(`/api/v1/product/groups/${id}/reports/debts?actor_user_id=${actor}`),
  settlementPlan: async (id: number) => DEMO_MODE ? demoDebtReport(id).transfers : request<any[]>(`/api/v1/groups/${id}/settlement-plan`),
  paymentProfile: async (id: number) => DEMO_MODE ? ({ bank_name: 'ملت', account_holder: 'ساجد فلاح', card_number: '610433******1234' }) : request<any>(`/api/v1/product/users/${id}/payment-profile`),
  createExpense: async (groupId: number, payload: any) => {
    if (DEMO_MODE) {
      const row: Expense = {
        id: Date.now(),
        title: payload.title,
        amount: String(payload.amount),
        category: payload.category,
        paid_by_user_id: payload.paid_by_user_id,
      }
      demoExpenses[groupId] = [row, ...(demoExpenses[groupId] || [])]
      return structuredClone(row)
    }
    return request(`/api/v1/groups/${groupId}/expenses`, { method: 'POST', body: JSON.stringify(payload) })
  },
}
