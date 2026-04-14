import api from './api';

export interface WorkflowDefinition {
  nodes: any[];
  edges: any[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  workflow?: WorkflowDefinition;
}

export interface AIResponse {
  message: string;
  workflow?: WorkflowDefinition;
}

interface GenerateWorkflowApiResponse {
  definition?: WorkflowDefinition;
  workflow?: WorkflowDefinition | { definition?: WorkflowDefinition };
  message?: string;
}

const MAX_PROMPT_LENGTH = 1500;
const SAFETY_PROMPT_LENGTH = 1450;

class AIService {
  private buildPrompt(trimmedPrompt: string, currentWorkflow?: WorkflowDefinition): string {
    if (!currentWorkflow?.nodes?.length) {
      return trimmedPrompt.slice(0, SAFETY_PROMPT_LENGTH);
    }

    // Keep context concise so it stays within backend prompt limits.
    const nodeTypes = currentWorkflow.nodes
      .slice(0, 20)
      .map((node: any) => node.type)
      .filter(Boolean)
      .join(', ');

    const edgeCount = Array.isArray(currentWorkflow.edges) ? currentWorkflow.edges.length : 0;
    const contextSuffix = `\n\nCurrent canvas summary: node_types=[${nodeTypes || 'none'}], total_nodes=${currentWorkflow.nodes.length}, total_edges=${edgeCount}`;
    const allowedPromptLength = Math.max(0, SAFETY_PROMPT_LENGTH - contextSuffix.length);
    return `${trimmedPrompt.slice(0, allowedPromptLength)}${contextSuffix}`.slice(0, MAX_PROMPT_LENGTH);
  }

  private extractDefinition(data: GenerateWorkflowApiResponse | any): WorkflowDefinition | null {
    const candidate =
      data?.definition ||
      data?.workflow?.definition ||
      data?.workflow ||
      (data?.nodes && data?.edges ? data : null);

    if (
      candidate &&
      Array.isArray(candidate.nodes) &&
      Array.isArray(candidate.edges)
    ) {
      return candidate as WorkflowDefinition;
    }

    return null;
  }
  
  async generateWorkflow(
    prompt: string,
    currentWorkflow?: WorkflowDefinition,
  ): Promise<AIResponse> {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      throw new Error('Prompt cannot be empty.');
    }

    const contextualPrompt = this.buildPrompt(trimmedPrompt, currentWorkflow);

    const response = await api.post<GenerateWorkflowApiResponse>(
      '/ai/generate-workflow',
      { prompt: contextualPrompt },
    );

    const definition = this.extractDefinition(response.data);
    if (!definition) {
      throw new Error('AI generation returned no workflow definition.');
    }

    return {
      message: response.data?.message || 'Workflow generated from backend AI service.',
      workflow: definition,
    };
  }
}

export const aiService = new AIService();
