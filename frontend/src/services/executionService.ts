import api from './api';

export interface RunFormPayload {
  form_data: Record<string, any>;
}

export interface NodeExecutionResult {
  node_id: string;
  node_type: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | string;
  input_data: Record<string, any> | any[] | null;
  output_data: Record<string, any> | any[] | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExecutionDetail {
  id: string;
  workflow_id: string;
  user_id: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | string;
  triggered_by: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  node_results: NodeExecutionResult[];
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

  getExecution: async (executionId: string): Promise<ExecutionDetail> => {
    const response = await api.get(`/executions/${executionId}`);
    return response.data;
  },

  getLatestExecution: async (workflowId: string): Promise<ExecutionDetail> => {
    const response = await api.get(`/workflows/${workflowId}/executions/latest`);
    return response.data;
  },

  listExecutions: async (workflowId?: string): Promise<any> => {
    const params = workflowId ? { workflow_id: workflowId } : {};
    const response = await api.get(`/executions`, { params });
    return response.data;
  },

  executeNode: async (
    workflowId: string,
    nodeId: string,
    inputData?: Record<string, any> | null,
  ): Promise<any> => {
    const response = await api.post(
      `/workflows/${workflowId}/nodes/${nodeId}/execute`,
      { input_data: inputData ?? null },
    );
    return response.data;
  },
};
