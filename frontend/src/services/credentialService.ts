import api from './api';

export interface CredentialItem {
  id: string;
  user_id: string;
  app_name: string;
  created_at: string;
}

interface CredentialListResponse {
  credentials: CredentialItem[];
}

interface CreateCredentialPayload {
  app_name: string;
  token_data: Record<string, any>;
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
};
