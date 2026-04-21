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
  is_active?: boolean;
}

export interface WorkflowPublicRunUrl {
  node_id: string;
  path_token: string;
  is_active: boolean;
  method: string;
  path: string;
  url: string;
}

export interface PublicFormField {
  name: string;
  label: string;
  type: string;
  required: boolean;
}

export interface PublicFormDefinition {
  workflow_id: string;
  workflow_name: string;
  path_token: string;
  submit_url: string;
  form_node_id: string;
  form_title: string;
  form_description: string;
  fields: PublicFormField[];
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
    const action = isPublished ? 'publish' : 'unpublish';
    const response = await api.post(`/workflows/${id}/${action}`);
    return response.data;
  },

  /**
   * Update active status (used for execution polling toggle in canvas).
   */
  updateActiveStatus: async (id: string, isActive: boolean): Promise<any> => {
    const response = await api.put(`/workflows/${id}`, {
      is_active: isActive,
    });
    return response.data;
  },

  /**
   * Get workflow public run URL (stable webhook token URL).
   */
  getPublicRunUrl: async (id: string): Promise<WorkflowPublicRunUrl> => {
    const response = await api.get(`/workflows/${id}/public-run-url`);
    return response.data;
  },

  /**
   * Get token-based public form definition for published workflows.
   */
  getPublicFormDefinition: async (pathToken: string): Promise<PublicFormDefinition> => {
    const response = await api.get(`/public/forms/${pathToken}`);
    return response.data;
  },

  /**
   * Submit token-based public form.
   */
  submitPublicForm: async (
    pathToken: string,
    formData: Record<string, any>,
  ): Promise<{ execution_id: string; message: string }> => {
    const response = await api.post(`/public/forms/${pathToken}/submit`, {
      form_data: formData,
    });
    return response.data;
  }
};
