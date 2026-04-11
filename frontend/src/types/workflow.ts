import { Node, Edge } from 'reactflow';

export interface WorkflowNodeData {
  label: string;
  type: string; // The specific node type (e.g., 'manual_trigger'), matches Backend ID
  category: 'trigger' | 'action' | 'transform' | 'ai';
  config: Record<string, any>;
  is_dummy?: boolean;
  last_output?: any;
  status?: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | string;
  last_execution_result?: any;
}

export type WorkflowNode = Node<WorkflowNodeData>;
export type WorkflowEdge = Edge & {
  branch?: string;
};

export interface HealthCheckResponse {
  status: string;
  uptime: number;
}
