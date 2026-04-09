export interface User {
  id: string;
  email: string;
  username: string;
  created_at: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  // Actions
  setAuth: (user: User, token: string) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
  updateUser: (user: User) => void;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface SignupResponse {
  id: string;
  email: string;
  username: string;
}
