import { telegramInitData } from './telegram'

export type User = { id: number; telegram_id?: number; display_name: string }
export type Group = { id: number; name: string; raw_name?: string; role?: string; owner_user_id: number; currency: string }
export type Member = { user_id: number; display_name: string; role: string; telegram_id?: number }
export type Expense = { id: number; title: string; amount: string; category?: string; paid_by_name?: string; paid_by_user_id?: number; split_mode?: string }
export type Settlement = { id: number; group_id: number; from_user_id: number; to_user_id: number; amount: string; status: string; created_at?: string; responded_at?: string | null }
export type PaymentProfile = {
  user_id?: number
  display_name?: string
  bank_name?: string | null
  account_holder?: string | null
  card_number?: string | null
  iban?: string | null
  account_number?: string | null
  reminder_enabled: boolean
}
export type InvitePayload = { group_id: number; group_name: string; start_parameter: string }
export type GroupCategory = { id: number; group_id: number; name: string }

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const isLocalhost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
export const DEMO_MODE = isLocalhost && !window.Telegram?.WebApp?.initData
export const BOT_USERNAME = String(import.meta.env.VITE_BOT_USERNAME || '').replace(/^@/, '')

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
    { id: 1, title: 'شام رستوران', amount: '1850000', category: 'food', paid_by_user_id: 1, split_mode: 'equal' },
    { id: 2, title: 'تاکسی', amount: '420000', category: 'transport', paid_by_user_id: 2, split_mode: 'equal' },
    { id: 3, title: 'هتل', amount: '6200000', category: 'stay', paid_by_user_id: 3, split_mode: 'equal' },
    { id: 4, title: 'تفریحات ساحلی', amount: '1680000', category: 'entertainment', paid_by_user_id: 1, split_mode: 'equal' },
    { id: 5, title: 'بنزین', amount: '2650000', category: 'fuel', paid_by_user_id: 2, split_mode: 'equal' },
  ],
  102: [
    { id: 6, title: 'خرید هفتگی', amount: '3200000', category: 'shopping', paid_by_user_id: 1, split_mode: 'equal' },
    { id: 7, title: 'قبض اینترنت', amount: '650000', category: 'other', paid_by_user_id: 5, split_mode: 'equal' },
  ],
}
const demoProfiles: Record<number, PaymentProfile> = {
  1: { user_id: 1, display_name: 'ساجد فلاح', bank_name: 'ملت', account_holder: 'ساجد فلاح', card_number: '6104337812341234', iban: 'IR120000000000000000000001', account_number: '1234567890', reminder_enabled: true },
  2: { user_id: 2, display_name: 'علی', bank_name: 'ملی', account_holder: 'علی رضایی', card_number: '6037990012345678', iban: null, account_number: null, reminder_enabled: true },
  3: { user_id: 3, display_name: 'رضا', bank_name: 'سامان', account_holder: 'رضا محمدی', card_number: '6219861012345678', iban: null, account_number: null, reminder_enabled: true },
  4: { user_id: 4, display_name: 'محمد', bank_name: 'پاسارگاد', account_holder: 'محمد احمدی', card_number: '5022291012345678', iban: null, account_number: null, reminder_enabled: true },
}
const demoCategories: Record<number, GroupCategory[]> = {
  101: [{ id: 1, group_id: 101, name: 'کافه' }, { id: 2, group_id: 101, name: 'تفریحات آبی' }],
  102: [{ id: 3, group_id: 102, name: 'قبوض' }],
}
const demoSettlements: Record<number, Settlement[]> = {
  101: [{ id: 201, group_id: 101, from_user_id: 2, to_user_id: 1, amount: '1200000', status: 'pending', created_at: new Date().toISOString() }],
  102: [],
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
  if (groupId !== 101) return { balances: [], transfers: [] }
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
  createGroup: async (ownerUserId: number, name: string, currency = 'IRR') => {
    if (DEMO_MODE) {
      const group: Group = { id: Math.max(102, ...demoGroups.map(g => g.id)) + 1, name, raw_name: name, role: 'owner', owner_user_id: ownerUserId, currency }
      demoGroups.unshift(group)
      demoMembers[group.id] = [{ user_id: ownerUserId, display_name: demoUser.display_name, role: 'owner' }]
      demoExpenses[group.id] = []
      demoSettlements[group.id] = []
      demoCategories[group.id] = []
      return structuredClone(group)
    }
    const group = await request<Group>('/api/v1/groups', { method: 'POST', body: JSON.stringify({ name, owner_user_id: ownerUserId, currency }) })
    return { ...group, raw_name: group.name, role: 'owner' }
  },
  summary: async (userId: number) => DEMO_MODE ? ({ owned_active_groups: demoGroups.length, total_memberships: demoGroups.length, free_owned_group_limit: 2, remaining_free_groups: Math.max(0, 2 - demoGroups.length) }) : request<any>(`/api/v1/dashboard/users/${userId}/summary`),
  group: async (id: number) => DEMO_MODE ? structuredClone(demoGroups.find(g => g.id === id)!) : request<Group>(`/api/v1/groups/${id}`),
  members: async (id: number) => DEMO_MODE ? structuredClone(demoMembers[id] || []) : request<Member[]>(`/api/v1/groups/${id}/members`),
  expenses: async (id: number) => DEMO_MODE ? structuredClone(demoExpenses[id] || []) : request<Expense[]>(`/api/v1/groups/${id}/expenses?limit=100`),
  expenseReport: async (id: number, actor: number) => DEMO_MODE ? demoExpenseReport(id) : request<any>(`/api/v1/product/groups/${id}/reports/expenses?actor_user_id=${actor}`),
  debtReport: async (id: number, actor: number) => DEMO_MODE ? demoDebtReport(id) : request<any>(`/api/v1/product/groups/${id}/reports/debts?actor_user_id=${actor}`),
  invite: async (id: number, actor: number): Promise<InvitePayload> => DEMO_MODE
    ? { group_id: id, group_name: demoGroups.find(g => g.id === id)?.raw_name || 'حساب دمو', start_parameter: `join_demo_${id}` }
    : request(`/api/v1/product/groups/${id}/invite?actor_user_id=${actor}`),
  categories: async (id: number, actor: number) => DEMO_MODE ? structuredClone(demoCategories[id] || []) : request<GroupCategory[]>(`/api/v1/management/groups/${id}/categories?actor_user_id=${actor}`),
  settlementPlan: async (id: number) => DEMO_MODE ? demoDebtReport(id).transfers : request<any[]>(`/api/v1/groups/${id}/settlement-plan`),
  pendingSettlements: async (id: number, actor: number) => DEMO_MODE
    ? structuredClone((demoSettlements[id] || []).filter(s => s.status === 'pending' && (s.from_user_id === actor || s.to_user_id === actor)))
    : request<Settlement[]>(`/api/v1/groups/${id}/settlements/pending?actor_user_id=${actor}`),
  requestSettlement: async (id: number, payload: { actor_user_id: number; from_user_id: number; to_user_id: number; amount: string | number }) => {
    if (DEMO_MODE) {
      const existing = (demoSettlements[id] || []).find(s => s.status === 'pending' && s.from_user_id === payload.from_user_id && s.to_user_id === payload.to_user_id && Number(s.amount) === Number(payload.amount))
      if (existing) return structuredClone(existing)
      const row: Settlement = { id: Date.now(), group_id: id, from_user_id: payload.from_user_id, to_user_id: payload.to_user_id, amount: String(payload.amount), status: 'pending', created_at: new Date().toISOString() }
      demoSettlements[id] = [row, ...(demoSettlements[id] || [])]
      return structuredClone(row)
    }
    return request<Settlement>(`/api/v1/groups/${id}/settlements`, { method: 'POST', body: JSON.stringify(payload) })
  },
  confirmSettlement: async (groupId: number, settlementId: number, actor: number) => {
    if (DEMO_MODE) {
      const row = (demoSettlements[groupId] || []).find(s => s.id === settlementId)
      if (row) { row.status = 'confirmed'; row.responded_at = new Date().toISOString() }
      return structuredClone(row!)
    }
    return request<Settlement>(`/api/v1/groups/${groupId}/settlements/${settlementId}/confirm`, { method: 'POST', body: JSON.stringify({ actor_user_id: actor }) })
  },
  rejectSettlement: async (groupId: number, settlementId: number, actor: number) => {
    if (DEMO_MODE) {
      const row = (demoSettlements[groupId] || []).find(s => s.id === settlementId)
      if (row) { row.status = 'rejected'; row.responded_at = new Date().toISOString() }
      return structuredClone(row!)
    }
    return request<Settlement>(`/api/v1/groups/${groupId}/settlements/${settlementId}/reject`, { method: 'POST', body: JSON.stringify({ actor_user_id: actor }) })
  },
  paymentProfile: async (id: number) => DEMO_MODE ? structuredClone(demoProfiles[id] || { user_id: id, reminder_enabled: true }) : request<PaymentProfile>(`/api/v1/product/users/${id}/payment-profile`),
  savePaymentProfile: async (id: number, profile: PaymentProfile) => {
    if (DEMO_MODE) { demoProfiles[id] = { ...profile, user_id: id }; return structuredClone(demoProfiles[id]) }
    return request<PaymentProfile>(`/api/v1/product/users/${id}/payment-profile`, { method: 'PUT', body: JSON.stringify(profile) })
  },
  createExpense: async (groupId: number, payload: any) => {
    if (DEMO_MODE) {
      const row: Expense = { id: Date.now(), title: payload.title, amount: String(payload.amount), category: payload.category, paid_by_user_id: payload.paid_by_user_id, split_mode: payload.split_mode }
      demoExpenses[groupId] = [row, ...(demoExpenses[groupId] || [])]
      return structuredClone(row)
    }
    return request(`/api/v1/groups/${groupId}/expenses`, { method: 'POST', body: JSON.stringify(payload) })
  },
}
