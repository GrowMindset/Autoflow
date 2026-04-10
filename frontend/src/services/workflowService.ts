import api from './api';

export interface WorkflowDefinition {
  nodes: any[];
  edges: any[];
}

export interface WorkflowSaveData {
  id?: string;
  name: string;
  description?: string;
  definition: WorkflowDefinition;
  is_published?: boolean;
}

export const workflowService = {
  /**
   * Save workflow to backend
   */
  saveWorkflow: async (data: WorkflowSaveData): Promise<any> => {
    // If it has a UUID-like ID, it's an update, otherwise it might be a new workflow
    const isUpdate = data.id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.id);
    
    if (isUpdate) {
      const response = await api.put(`/workflows/${data.id}`, {
        name: data.name,
        description: data.description || '',
        definition: data.definition,
        is_published: data.is_published
      });
      return response.data;
    } else {
      const response = await api.post('/workflows', {
        name: data.name,
        description: data.description || '',
        definition: data.definition
      });
      return response.data;
    }
  },

  /**
   * Get all workflows from backend
   */
  getWorkflows: async (limit = 20, offset = 0): Promise<any[]> => {
    try {
      const response = await api.get('/workflows', {
        params: { limit, offset }
      });
      return response.data.workflows || [];
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
      return [];
    }
  },

  /**
   * Get a specific workflow by ID from backend
   */
  getWorkflow: async (id: string): Promise<any | null> => {
    try {
      const response = await api.get(`/workflows/${id}`);
      return response.data;
    } catch (error) {
      console.error(`Failed to fetch workflow ${id}:`, error);
      return null;
    }
  },

  /**
   * Delete a workflow
   */
  deleteWorkflow: async (id: string): Promise<void> => {
    await api.delete(`/workflows/${id}`);
  },

  /**
   * Update publish status specifically
   */
  updatePublishStatus: async (id: string, isPublished: boolean): Promise<any> => {
    const response = await api.put(`/workflows/${id}`, {
      is_published: isPublished
    });
    return response.data;
  }
};
