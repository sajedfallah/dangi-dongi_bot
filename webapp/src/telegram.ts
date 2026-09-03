declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        initDataUnsafe?: { user?: { id: number; first_name?: string; last_name?: string; username?: string; photo_url?: string } }
        colorScheme?: 'light' | 'dark'
        ready(): void
        expand(): void
        close(): void
        HapticFeedback?: { impactOccurred(style: 'light' | 'medium' | 'heavy'): void }
        openTelegramLink?(url: string): void
      }
    }
  }
}

export const tg = window.Telegram?.WebApp

export function initTelegram() {
  tg?.ready()
  tg?.expand()
}

export function telegramInitData() {
  return tg?.initData || ''
}

export function telegramUser() {
  return tg?.initDataUnsafe?.user
}

export function haptic() {
  tg?.HapticFeedback?.impactOccurred('light')
}
