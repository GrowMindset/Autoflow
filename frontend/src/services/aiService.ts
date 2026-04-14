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
  definition: WorkflowDefinition;
}

class AIService {
  async generateWorkflow(
    prompt: string,
    currentWorkflow?: WorkflowDefinition,
  ): Promise<AIResponse> {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      throw new Error('Prompt cannot be empty.');
    }

    let contextualPrompt = trimmedPrompt;

    // Keep context concise so it fits backend prompt limits.
    if (currentWorkflow?.nodes?.length) {
      const nodeTypes = currentWorkflow.nodes
        .slice(0, 25)
        .map((node: any) => node.type)
        .filter(Boolean)
        .join(', ');

      contextualPrompt = `${trimmedPrompt}\n\nCurrent workflow node types: ${nodeTypes || 'none'}`;
    }

    const response = await api.post<GenerateWorkflowApiResponse>(
      '/ai/generate-workflow',
      { prompt: contextualPrompt },
    );

    const definition = response.data?.definition;
    if (!definition) {
      throw new Error('AI generation returned no workflow definition.');
    }

    return {
      message: 'Workflow generated from backend AI service.',
      workflow: definition,
    };
  }
}

export const aiService = new AIService();
