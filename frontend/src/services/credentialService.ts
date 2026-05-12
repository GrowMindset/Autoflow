import api from './api';

export interface CredentialItem {
  id: string;
  user_id: string;
  app_name: string;
  created_at: string;
  provider?: string | null;
  display_name?: string | null;
  description?: string | null;
}

interface CredentialListResponse {
  credentials: CredentialItem[];
}

interface CreateCredentialPayload {
  app_name: string;
  token_data: Record<string, any>;
  description?: string;
}

interface GoogleOAuthStartResponse {
  auth_url: string;
  state: string;
  redirect_uri: string;
  app_name: string;
  scopes: string[];
}

type OAuthStartResponse = Omit<GoogleOAuthStartResponse, 'app_name'> & { app_name?: string };

interface GoogleOAuthExchangePayload {
  code: string;
  state: string;
  redirect_uri?: string;
}

export const credentialService = {
  async list(appName?: string): Promise<CredentialItem[]> {
    const response = await api.get<CredentialListResponse>('/credentials', {
      params: appName ? { app_name: appName } : undefined,
    });
    return Array.isArray(response.data?.credentials) ? response.data.credentials : [];
  },

  async create(payload: CreateCredentialPayload): Promise<CredentialItem> {
    const response = await api.post<CredentialItem>('/credentials', payload);
    return response.data;
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/credentials/${id}`);
  },

  async startGoogleOAuth(appName: 'gmail' | 'sheets' | 'docs', redirectUri?: string): Promise<GoogleOAuthStartResponse> {
    const response = await api.get<GoogleOAuthStartResponse>('/credentials/oauth/google/start', {
      params: {
        app_name: appName,
        ...(redirectUri ? { redirect_uri: redirectUri } : {}),
      },
    });
    return response.data;
  },

  async exchangeGoogleOAuth(payload: GoogleOAuthExchangePayload): Promise<CredentialItem> {
    const response = await api.post<CredentialItem>('/credentials/oauth/google/exchange', payload);
    return response.data;
  },

  async startLinkedInOAuth(redirectUri?: string): Promise<OAuthStartResponse> {
    const response = await api.get<OAuthStartResponse>('/credentials/oauth/linkedin/start', {
      params: {
        ...(redirectUri ? { redirect_uri: redirectUri } : {}),
      },
    });
    return response.data;
  },

  async exchangeLinkedInOAuth(payload: GoogleOAuthExchangePayload): Promise<CredentialItem> {
    const response = await api.post<CredentialItem>('/credentials/oauth/linkedin/exchange', payload);
    return response.data;
  },
};
