import api from './api';

export interface RunFormPayload {
  form_data: Record<string, string>;
}

export const executionService = {
  runWorkflowForm: async (workflowId: string, payload: RunFormPayload): Promise<any> => {
    const response = await api.post(`/workflows/${workflowId}/run-form`, payload);
    return response.data;
  },

  getExecution: async (executionId: string): Promise<any> => {
    const response = await api.get(`/executions/${executionId}`);
    return response.data;
  },

  executeNode: async (workflowId: string, nodeId: string, inputData: any): Promise<any> => {
    const response = await api.post(`/workflows/${workflowId}/nodes/${nodeId}/execute`, {
      input_data: inputData,
    });
    return response.data;
  },
};
