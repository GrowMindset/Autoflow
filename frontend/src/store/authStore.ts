import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AuthState, User } from '../types/auth';

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      setAuth: (user: User, token: string, refreshToken: string) => {
        localStorage.setItem('token', token);
        localStorage.setItem('refresh_token', refreshToken);
        set({
          user,
          token,
          refreshToken,
          isAuthenticated: true,
          isLoading: false,
        });
      },

      setTokenPair: (token: string, refreshToken: string) => {
        localStorage.setItem('token', token);
        localStorage.setItem('refresh_token', refreshToken);
        set((state) => ({
          ...state,
          token,
          refreshToken,
          isAuthenticated: Boolean(state.user),
        }));
      },

      clearAuth: () => {
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        set({
          user: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
      },

      setLoading: (isLoading: boolean) => set({ isLoading }),

      updateUser: (user: User) => set({ user }),
    }),
    {
      name: 'autoflow-auth-storage',
      storage: createJSONStorage(() => localStorage),
      // We only want to persist some parts of the state
      partialize: (state) => ({ 
        user: state.user, 
        token: state.token, 
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated 
      }),
    }
  )
);
