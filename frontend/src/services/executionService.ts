import api from './api';

export interface RunFormPayload {
  form_data: Record<string, string>;
}

export const executionService = {
  runWorkflowForm: async (workflowId: string, payload: RunFormPayload): Promise<any> => {
    const response = await api.post(`/workflows/${workflowId}/run-form`, payload);
    return response.data;
  },

  runWorkflow: async (workflowId: string): Promise<any> => {
    const response = await api.post(`/workflows/${workflowId}/run`);
    return response.data;
  },

  getExecution: async (executionId: string): Promise<any> => {
    const response = await api.get(`/executions/${executionId}`);
    return response.data;
  },

  getLatestExecution: async (workflowId: string): Promise<any> => {
    const response = await api.get(`/workflows/${workflowId}/executions/latest`);
    return response.data;
  },
};
