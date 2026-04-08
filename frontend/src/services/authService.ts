import api from './api';
import { LoginResponse, SignupResponse, User } from '../types/auth';

export const authService = {
  /**
   * Login user and get JWT token
   */
  login: async (credentials: any): Promise<LoginResponse> => {
    // FastAPI OAuth2PasswordRequestForm expects form-data with 'username' and 'password'
    const formData = new URLSearchParams();
    formData.append('username', credentials.email || credentials.username);
    formData.append('password', credentials.password);

    const response = await api.post<LoginResponse>('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    });
    return response.data;
  },

  /**
   * Register a new user
   */
  signup: async (data: any): Promise<SignupResponse> => {
    const response = await api.post<SignupResponse>('/auth/signup', data);
    return response.data;
  },

  /**
   * Get current authenticated user details
   */
  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  }
};
