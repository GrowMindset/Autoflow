import api from './api';

export interface WorkflowDefinition {
  nodes: any[];
  edges: any[];
}

export type AssistantMode = 'clarify' | 'generate' | 'modify' | 'ask';
export type AssistantInteractionMode = 'build' | 'ask';

export interface ClarificationQuestion {
  id: string;
  question: string;
  reason: string;
}

export interface ConversationState {
  confirmedChoices: Record<string, string>;
  assumptions: string[];
  recentMessages: Array<{ role: 'user' | 'assistant'; content: string }>;
  workflowContextOrigin?: 'accepted_canvas' | 'preview' | 'unknown';
  previewActive?: boolean;
  lastAcceptedWorkflowSignature?: string;
  lastReferencedNodes?: string[];
  lastUnresolvedQuestion?: string;
  lastMode?: AssistantMode;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  mode?: AssistantMode;
  questions?: ClarificationQuestion[];
  assumptions?: string[];
  changeSummary?: string;
  workflow?: WorkflowDefinition;
  workflowName?: string;
}

export interface AIResponse {
  mode: AssistantMode;
  message: string;
  questions: ClarificationQuestion[];
  assumptions: string[];
  changeSummary?: string;
  conversationState: ConversationState;
  workflow?: WorkflowDefinition;
  workflowName?: string;
}

interface AssistWorkflowOptions {
  signal?: AbortSignal;
}

export interface AIChatHistoryPayload {
  scopeKey: string;
  messages: Message[];
  conversationState: ConversationState;
}

interface AssistantApiQuestion {
  id?: string;
  question?: string;
  reason?: string;
}

interface AssistantApiResponse {
  mode?: AssistantMode;
  assistant_message?: string;
  questions?: AssistantApiQuestion[];
  assumptions?: string[];
  change_summary?: string;
  definition?: WorkflowDefinition;
  workflow?: WorkflowDefinition | { definition?: WorkflowDefinition };
  name?: string;
  workflow_name?: string;
  title?: string;
}

interface AssistantApiConversationState {
  confirmed_choices?: Record<string, string>;
  assumptions?: string[];
  recent_messages?: Array<{ role?: string; content?: string }>;
  workflow_context_origin?: 'accepted_canvas' | 'preview' | 'unknown';
  preview_active?: boolean;
  last_accepted_workflow_signature?: string;
  last_referenced_nodes?: string[];
  last_unresolved_question?: string;
  last_mode?: AssistantMode;
}

interface AIChatHistoryApiResponse {
  scope_key?: string;
  messages?: Record<string, any>[];
  conversation_state?: Record<string, any>;
}

interface AIChatHistoryClearApiResponse {
  message?: string;
  deleted_messages?: number;
  deleted_states?: number;
}

const MAX_PROMPT_LENGTH = 4000;
const SAFETY_PROMPT_LENGTH = 3900;
const MAX_SIGNATURE_LENGTH = 240;
const MAX_UNRESOLVED_QUESTION_LENGTH = 400;

const clampText = (value: unknown, maxLength: number): string =>
  String(value || '').trim().slice(0, maxLength);

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

  private extractDefinition(data: AssistantApiResponse | any): WorkflowDefinition | null {
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

  private extractWorkflowName(data: AssistantApiResponse | any): string | undefined {
    const candidates = [
      data?.name,
      data?.workflow_name,
      data?.title,
      data?.workflow?.name,
      data?.workflow?.workflow_name,
    ];

    for (const candidate of candidates) {
      if (typeof candidate !== 'string') continue;
      const normalized = candidate.trim();
      if (normalized) {
        return normalized.slice(0, 100);
      }
    }
    return undefined;
  }

  private collectReferencedNodes(prompt: string, currentWorkflow?: WorkflowDefinition): string[] {
    const lowered = ` ${String(prompt || '').toLowerCase()} `;
    if (!currentWorkflow?.nodes?.length) return [];

    const matches: string[] = [];
    const seen = new Set<string>();
    for (const node of currentWorkflow.nodes.slice(0, 120)) {
      const id = String(node?.id || '').trim();
      const label = String(node?.label || '').trim().toLowerCase();
      const type = String(node?.type || '').trim().toLowerCase();
      const aliases = [id.toLowerCase(), label, type, type.replace(/_/g, ' ')].filter(Boolean);
      const hit = aliases.some((alias) => alias && lowered.includes(` ${alias} `));
      if (!hit) continue;
      const key = id || type;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      matches.push(key);
      if (matches.length >= 6) break;
    }
    return matches;
  }

  private mergeReferencedNodes(previous: string[] | undefined, current: string[]): string[] {
    const merged: string[] = [];
    const seen = new Set<string>();
    for (const item of [...(current || []), ...(previous || [])]) {
      const normalized = String(item || '').trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      merged.push(normalized);
      if (merged.length >= 6) break;
    }
    return merged;
  }
  
  async assistWorkflow(
    prompt: string,
    currentWorkflow?: WorkflowDefinition,
    conversationState?: ConversationState,
    interactionMode: AssistantInteractionMode = 'build',
    options?: AssistWorkflowOptions,
  ): Promise<AIResponse> {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      throw new Error('Prompt cannot be empty.');
    }

    const contextualPrompt = this.buildPrompt(trimmedPrompt, currentWorkflow);
    const currentReferencedNodes = this.collectReferencedNodes(trimmedPrompt, currentWorkflow);
    const mergedReferencedNodes = this.mergeReferencedNodes(
      conversationState?.lastReferencedNodes,
      currentReferencedNodes,
    );

    const statePayload: AssistantApiConversationState = {
      confirmed_choices: conversationState?.confirmedChoices || {},
      assumptions: conversationState?.assumptions || [],
      recent_messages: Array.isArray(conversationState?.recentMessages)
        ? conversationState?.recentMessages
            .slice(-12)
            .map((item) => ({
              role: item?.role === 'assistant' ? 'assistant' : 'user',
              content: String(item?.content || '').trim().slice(0, 500),
            }))
            .filter((item) => Boolean(item.content))
        : [],
      workflow_context_origin: conversationState?.workflowContextOrigin || 'accepted_canvas',
      preview_active: Boolean(conversationState?.previewActive),
      last_accepted_workflow_signature:
        clampText(conversationState?.lastAcceptedWorkflowSignature, MAX_SIGNATURE_LENGTH) || undefined,
      last_referenced_nodes: mergedReferencedNodes,
      last_unresolved_question:
        clampText(conversationState?.lastUnresolvedQuestion, MAX_UNRESOLVED_QUESTION_LENGTH) || undefined,
      last_mode: conversationState?.lastMode,
    };

    const response = await api.post<AssistantApiResponse>(
      '/ai/workflow-assistant',
      {
        prompt: contextualPrompt,
        interaction_mode: interactionMode,
        current_definition: currentWorkflow,
        conversation_state: statePayload,
      },
      {
        signal: options?.signal,
      },
    );

    const mode: AssistantMode = response.data?.mode || 'generate';
    const definition = this.extractDefinition(response.data);
    if ((mode === 'generate' || mode === 'modify') && !definition) {
      throw new Error('AI assistant returned no workflow definition for generation mode.');
    }

    const questions: ClarificationQuestion[] = Array.isArray(response.data?.questions)
      ? response.data.questions
          .map((item): ClarificationQuestion | null => {
            const id = String(item?.id || '').trim();
            const question = String(item?.question || '').trim();
            const reason = String(item?.reason || '').trim();
            if (!id || !question || !reason) return null;
            return { id, question, reason };
          })
          .filter((item): item is ClarificationQuestion => Boolean(item))
      : [];

    const assumptions = Array.isArray(response.data?.assumptions)
      ? response.data.assumptions.map((item) => String(item || '').trim()).filter(Boolean)
      : [];

    const normalizedMessage = String(response.data?.assistant_message || '').trim();
    const fallbackMessage = mode === 'clarify'
      ? 'I need a little more workflow detail before generating.'
      : mode === 'ask'
        ? 'Here is Autoflow guidance based on your question.'
        : 'Workflow generated from backend AI service.';

    const nextUnresolvedQuestion =
      mode === 'clarify'
        ? trimmedPrompt.slice(0, MAX_UNRESOLVED_QUESTION_LENGTH)
        : '';

    const nextConversationState: ConversationState = {
      confirmedChoices: conversationState?.confirmedChoices || {},
      assumptions,
      recentMessages: Array.isArray(conversationState?.recentMessages)
        ? conversationState.recentMessages
        : [],
      workflowContextOrigin: conversationState?.workflowContextOrigin || 'accepted_canvas',
      previewActive: Boolean(conversationState?.previewActive),
      lastAcceptedWorkflowSignature:
        clampText(conversationState?.lastAcceptedWorkflowSignature, MAX_SIGNATURE_LENGTH) || undefined,
      lastReferencedNodes: mergedReferencedNodes,
      lastUnresolvedQuestion: nextUnresolvedQuestion || undefined,
      lastMode: mode,
    };

    return {
      mode,
      message: normalizedMessage || fallbackMessage,
      questions,
      assumptions,
      changeSummary: typeof response.data?.change_summary === 'string'
        ? response.data.change_summary.trim() || undefined
        : undefined,
      conversationState: nextConversationState,
      workflow: definition || undefined,
      workflowName: this.extractWorkflowName(response.data),
    };
  }

  private normalizeConversationState(rawState: any): ConversationState {
    if (!rawState || typeof rawState !== 'object') {
      return {
        confirmedChoices: {},
        assumptions: [],
        recentMessages: [],
      };
    }

    const rawRecentMessages =
      Array.isArray(rawState.recentMessages) ? rawState.recentMessages :
      Array.isArray(rawState.recent_messages) ? rawState.recent_messages :
      [];

    return {
      confirmedChoices: rawState.confirmedChoices && typeof rawState.confirmedChoices === 'object'
        ? rawState.confirmedChoices
        : {},
      assumptions: Array.isArray(rawState.assumptions)
        ? rawState.assumptions.map((item: unknown) => String(item || '').trim()).filter(Boolean)
        : [],
      recentMessages: rawRecentMessages
        .map((item: any) => ({
          role: item?.role === 'assistant' ? 'assistant' : 'user',
          content: String(item?.content || '').trim(),
        }))
        .filter((item: any) => Boolean(item.content))
        .slice(-12),
      workflowContextOrigin:
        rawState.workflowContextOrigin === 'preview' || rawState.workflowContextOrigin === 'accepted_canvas' || rawState.workflowContextOrigin === 'unknown'
          ? rawState.workflowContextOrigin
          : rawState.workflow_context_origin === 'preview' || rawState.workflow_context_origin === 'accepted_canvas' || rawState.workflow_context_origin === 'unknown'
            ? rawState.workflow_context_origin
            : 'accepted_canvas',
      previewActive: Boolean(rawState.previewActive ?? rawState.preview_active ?? false),
      lastAcceptedWorkflowSignature: clampText(
        rawState.lastAcceptedWorkflowSignature
          ?? rawState.last_accepted_workflow_signature
          ?? '',
        MAX_SIGNATURE_LENGTH,
      ) || undefined,
      lastReferencedNodes: (
        Array.isArray(rawState.lastReferencedNodes)
          ? rawState.lastReferencedNodes
          : Array.isArray(rawState.last_referenced_nodes)
            ? rawState.last_referenced_nodes
            : []
      )
        .map((item: unknown) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, 12),
      lastUnresolvedQuestion: clampText(
        rawState.lastUnresolvedQuestion
          ?? rawState.last_unresolved_question
          ?? '',
        MAX_UNRESOLVED_QUESTION_LENGTH,
      ) || undefined,
      lastMode: (rawState.lastMode === 'clarify' || rawState.lastMode === 'generate' || rawState.lastMode === 'modify' || rawState.lastMode === 'ask')
        ? rawState.lastMode
        : undefined,
    };
  }

  private normalizeStoredMessage(rawMessage: any): Message | null {
    if (!rawMessage || typeof rawMessage !== 'object') return null;

    const id = String(rawMessage.id || '').trim();
    const role = String(rawMessage.role || '').trim();
    const content = String(rawMessage.content || '').trim();
    const timestamp = String(rawMessage.timestamp || '').trim();
    if (!id || !content || !timestamp || (role !== 'user' && role !== 'assistant')) {
      return null;
    }

    const normalized: Message = {
      id,
      role,
      content,
      timestamp,
    };

    if (rawMessage.mode === 'clarify' || rawMessage.mode === 'generate' || rawMessage.mode === 'modify' || rawMessage.mode === 'ask') {
      normalized.mode = rawMessage.mode;
    }

    if (Array.isArray(rawMessage.questions)) {
      normalized.questions = rawMessage.questions
        .map((item: any) => {
          const qId = String(item?.id || '').trim();
          const question = String(item?.question || '').trim();
          const reason = String(item?.reason || '').trim();
          if (!qId || !question || !reason) return null;
          return { id: qId, question, reason };
        })
        .filter(Boolean) as any;
    }

    if (Array.isArray(rawMessage.assumptions)) {
      normalized.assumptions = rawMessage.assumptions.map((item: any) => String(item || '').trim()).filter(Boolean);
    }
    if (typeof rawMessage.changeSummary === 'string' && rawMessage.changeSummary.trim()) {
      normalized.changeSummary = rawMessage.changeSummary.trim();
    }

    const workflow = this.extractDefinition(rawMessage);
    if (workflow) {
      normalized.workflow = workflow;
    }
    const workflowName = this.extractWorkflowName(rawMessage);
    if (workflowName) {
      normalized.workflowName = workflowName;
    }
    return normalized;
  }

  async getChatHistory(scopeKey: string): Promise<AIChatHistoryPayload> {
    const normalizedScope = String(scopeKey || '').trim();
    if (!normalizedScope) {
      throw new Error('scopeKey cannot be empty.');
    }

    const response = await api.get<AIChatHistoryApiResponse>(`/ai/chat-history/${encodeURIComponent(normalizedScope)}`);
    const rawMessages = Array.isArray(response.data?.messages) ? response.data.messages : [];
    const messages = rawMessages
      .map((item) => this.normalizeStoredMessage(item))
      .filter((item): item is Message => Boolean(item))
      .slice(-400);

    return {
      scopeKey: String(response.data?.scope_key || normalizedScope),
      messages,
      conversationState: this.normalizeConversationState(response.data?.conversation_state),
    };
  }

  async saveChatHistory(
    scopeKey: string,
    messages: Message[],
    conversationState: ConversationState,
  ): Promise<AIChatHistoryPayload> {
    const normalizedScope = String(scopeKey || '').trim();
    if (!normalizedScope) {
      throw new Error('scopeKey cannot be empty.');
    }

    const safeMessages = (Array.isArray(messages) ? messages : [])
      .slice(-400)
      .map((message) => ({
        ...message,
        id: String(message.id || '').trim(),
        role: message.role === 'assistant' ? 'assistant' : 'user',
        content: String(message.content || '').trim(),
        timestamp: String(message.timestamp || '').trim(),
      }))
      .filter((message) => Boolean(message.id && message.content && message.timestamp));

    const response = await api.put<AIChatHistoryApiResponse>(
      `/ai/chat-history/${encodeURIComponent(normalizedScope)}`,
      {
        messages: safeMessages,
        conversation_state: {
          confirmedChoices: conversationState?.confirmedChoices || {},
          assumptions: conversationState?.assumptions || [],
          recentMessages: Array.isArray(conversationState?.recentMessages)
            ? conversationState.recentMessages
                .slice(-12)
                .map((item) => ({
                  role: item?.role === 'assistant' ? 'assistant' : 'user',
                  content: String(item?.content || '').trim().slice(0, 500),
                }))
                .filter((item) => Boolean(item.content))
            : [],
          workflowContextOrigin: conversationState?.workflowContextOrigin || 'accepted_canvas',
          previewActive: Boolean(conversationState?.previewActive),
          lastAcceptedWorkflowSignature: clampText(
            conversationState?.lastAcceptedWorkflowSignature,
            MAX_SIGNATURE_LENGTH,
          ),
          lastReferencedNodes: Array.isArray(conversationState?.lastReferencedNodes)
            ? conversationState?.lastReferencedNodes.slice(0, 12)
            : [],
          lastUnresolvedQuestion: clampText(
            conversationState?.lastUnresolvedQuestion,
            MAX_UNRESOLVED_QUESTION_LENGTH,
          ),
          lastMode: conversationState?.lastMode,
        },
      },
    );

    const savedMessages = (Array.isArray(response.data?.messages) ? response.data.messages : [])
      .map((item) => this.normalizeStoredMessage(item))
      .filter((item): item is Message => Boolean(item));

    return {
      scopeKey: String(response.data?.scope_key || normalizedScope),
      messages: savedMessages,
      conversationState: this.normalizeConversationState(response.data?.conversation_state),
    };
  }

  async clearChatHistory(scopeKey: string): Promise<AIChatHistoryClearApiResponse> {
    const normalizedScope = String(scopeKey || '').trim();
    if (!normalizedScope) {
      throw new Error('scopeKey cannot be empty.');
    }
    const response = await api.delete<AIChatHistoryClearApiResponse>(`/ai/chat-history/${encodeURIComponent(normalizedScope)}`);
    return response.data || {};
  }

  async clearAllChatHistory(): Promise<AIChatHistoryClearApiResponse> {
    const response = await api.delete<AIChatHistoryClearApiResponse>('/ai/chat-history');
    return response.data || {};
  }
}

export const aiService = new AIService();
