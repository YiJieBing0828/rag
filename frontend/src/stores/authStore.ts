import { create } from 'zustand'

/** 认证态占位：后续第 11 章接入 JWT 时再扩展。 */
interface AuthState {
  user: { id: string; name: string } | null
  token: string | null
  setAuth: (user: AuthState['user'], token: string | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  setAuth: (user, token) => set({ user, token }),
  logout: () => set({ user: null, token: null }),
}))
