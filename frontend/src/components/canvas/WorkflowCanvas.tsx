import React, { useCallback, useRef, useState, useEffect, useMemo } from 'react';
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Connection,
  MarkerType,
  BackgroundVariant,
  ReactFlowInstance,
  XYPosition,
  ReactFlowProvider,
} from 'reactflow';
import dagre from 'dagre';

import 'reactflow/dist/style.css';
import { WorkflowNode, WorkflowEdge, WorkflowNodeData } from '../../types/workflow';
import BaseNode from './BaseNode';
import DeletableEdge from './DeletableEdge';
import { NODE_LIBRARY } from '../../constants/nodeLibrary';
import { createNode } from '../../utils/nodeFactory';
import ConfigPanel from '../config/ConfigPanel';
import { executionService, ExecutionDetail } from '../../services/executionService';
import { workflowService, WorkflowVersion } from '../../services/workflowService';
import toast from 'react-hot-toast';
import { useTheme } from '../../context/ThemeContext';
import { Play, Square, LayoutGrid, Sparkles, Search, Undo2, Redo2, Loader2, Plus } from 'lucide-react';
import { formatDateTimeInAppTimezone } from '../../utils/dateTime';
import { toUserFriendlyErrorMessage } from '../../utils/errorMessages';
import {
  FormErrors,
  FormFieldRenderer,
  FormValues,
  readFormValuesFromElement,
  validateFormValues,
} from '../forms/FormFieldRenderer';

const nodeTypes = {
  trigger: BaseNode,
  action: BaseNode,
  transform: BaseNode,
  input_output: BaseNode,
  utility: BaseNode,
  ai: BaseNode,
};

const edgeTypes = {
  deletable: DeletableEdge,
};

const AI_AGENT_CHILD_HANDLES = ['chat_model', 'memory', 'tool'] as const;
const AI_AGENT_CHILD_X_OFFSET: Record<string, number> = {
  chat_model: -130,
  memory: 0,
  tool: 130,
};
const AI_AGENT_CHILD_Y_OFFSET = 155;
const AI_AGENT_CHILD_STACK_GAP = 70;
const AUTO_LAYOUT_NODE_GAP = 40;
const AUTO_LAYOUT_RANK_GAP = 95;
const FORM_EXECUTION_MESSAGE_TYPE = 'autoflow:form-execution-started';
const EXECUTION_POLL_INTERVAL_MS = 300;
const EXTERNAL_EXECUTION_SYNC_INTERVAL_MS = 2500;
const UNDO_REDO_HISTORY_LIMIT = 100;
const UNDO_REDO_COMMIT_DEBOUNCE_MS = 180;
const AI_APPLY_PROCESS_MS = 950;
const AI_APPLY_HIGHLIGHT_MS = 2200;
const WORKFLOW_CLIPBOARD_VERSION = 1;
const WORKFLOW_CLIPBOARD_STORAGE_KEY = `autoflow:workflow-clipboard:v${WORKFLOW_CLIPBOARD_VERSION}`;
const DUPLICATE_NODE_OFFSET_X = 60;
const DUPLICATE_NODE_OFFSET_Y = 40;
const TRIGGER_NODE_TYPES = ['manual_trigger', 'form_trigger', 'schedule_trigger', 'webhook_trigger', 'workflow_trigger'] as const;
const WORKFLOW_INACTIVE_ERROR_MESSAGE = 'Workflow is inactive. Please activate workflow first.';
const PUBLISHED_WORKFLOW_EDIT_MESSAGE = 'Workflow is published. Unpublish to edit.';
const DEFAULT_LOOP_CONTROL = {
  enabled: false,
  max_node_executions: 3,
  max_total_node_executions: 500,
} as const;

const stripConfigEditorMetadata = (config: Record<string, any> | undefined): Record<string, any> => {
  const safeConfig = config && typeof config === 'object' && !Array.isArray(config)
    ? { ...config }
    : {};
  delete safeConfig.__af_mode;
  delete safeConfig.__af_values;
  return safeConfig;
};

const normalizeIfElseNodeConfig = (config: Record<string, any> | undefined): Record<string, any> => {
  const safeConfig = config && typeof config === 'object' && !Array.isArray(config)
    ? { ...config }
    : {};
  const conditionType = String(safeConfig.condition_type || '').trim().toUpperCase() === 'OR'
    ? 'OR'
    : 'AND';
  const rawConditions = Array.isArray(safeConfig.conditions) && safeConfig.conditions.length > 0
    ? safeConfig.conditions
    : [{
        field: safeConfig.field,
        operator: safeConfig.operator,
        value: safeConfig.value,
        value_mode: safeConfig.value_mode,
        value_field: safeConfig.value_field,
        case_sensitive: safeConfig.case_sensitive,
      }];
  const conditions = rawConditions.map((rawCondition: any, index: number) => {
    const condition = rawCondition && typeof rawCondition === 'object' ? rawCondition : {};
    const valueMode = String(condition.value_mode || 'literal').trim().toLowerCase() === 'field'
      ? 'field'
      : 'literal';
    return {
      id: String(condition.id || `condition_${index + 1}`),
      field: String(condition.field || ''),
      operator: String(condition.operator || 'equals').trim().toLowerCase() || 'equals',
      value: valueMode === 'field' ? '' : String(condition.value ?? ''),
      value_mode: valueMode,
      value_field: String(condition.value_field || ''),
      case_sensitive: parseBooleanLike(condition.case_sensitive, true),
    };
  });

  return {
    condition_type: conditionType,
    conditions: conditions.length > 0
      ? conditions
      : [{
          id: 'condition_1',
          field: '',
          operator: 'equals',
          value: '',
          value_mode: 'literal',
          value_field: '',
          case_sensitive: true,
        }],
  };
};

const parseBooleanLike = (rawValue: unknown, fallback = true): boolean => {
  if (rawValue === undefined || rawValue === null) return fallback;
  if (typeof rawValue === 'boolean') return rawValue;
  if (typeof rawValue === 'number') return rawValue !== 0;
  if (typeof rawValue === 'string') {
    const normalized = rawValue.trim().toLowerCase();
    if (!normalized) return fallback;
    if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
    if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  }
  return fallback;
};

const cloneNodeConfig = (config: Record<string, any> | undefined): Record<string, any> => {
  if (!config || typeof config !== 'object') return {};
  try {
    if (typeof structuredClone === 'function') {
      return structuredClone(config);
    }
  } catch (_error) {
    // Fallback to JSON clone below.
  }
  try {
    return JSON.parse(JSON.stringify(config));
  } catch (_error) {
    return { ...config };
  }
};

const buildCopiedLabel = (label: string, fallbackType: string): string => {
  const normalized = String(label || '').trim() || fallbackType.replace(/_/g, ' ');
  return /\(copy\)$/i.test(normalized) ? normalized : `${normalized} (Copy)`;
};

const sanitizeIdPrefix = (rawPrefix: string, fallback: string, maxLength = 32): string => {
  const normalized = String(rawPrefix || '')
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '');
  const candidate = normalized || fallback;
  return candidate.slice(0, maxLength) || fallback;
};

const generateUniqueNodeId = (existingIds: Set<string>, nodeType: string): string => {
  const safeType = sanitizeIdPrefix(nodeType, 'node', 32);
  let attempt = 0;
  let nextId = '';
  do {
    const timestampToken = Date.now().toString(36);
    const randomToken = Math.random().toString(36).slice(2, 8);
    const attemptToken = attempt > 0 ? `_${attempt.toString(36)}` : '';
    nextId = `${safeType}_${timestampToken}_${randomToken}${attemptToken}`;
    if (nextId.length > 100) {
      nextId = nextId.slice(0, 100);
    }
    attempt += 1;
  } while (existingIds.has(nextId));
  existingIds.add(nextId);
  return nextId;
};

const generateUniqueEdgeId = (existingIds: Set<string>): string => {
  let attempt = 0;
  let nextId = '';
  do {
    const timestampToken = Date.now().toString(36);
    const randomToken = Math.random().toString(36).slice(2, 8);
    const attemptToken = attempt > 0 ? `_${attempt.toString(36)}` : '';
    nextId = `e_${timestampToken}_${randomToken}${attemptToken}`;
    attempt += 1;
  } while (existingIds.has(nextId));
  existingIds.add(nextId);
  return nextId;
};

const readEdgeBranch = (edge: WorkflowEdge | any): string | undefined => {
  if (!edge || typeof edge !== 'object') return undefined;
  if (!Object.prototype.hasOwnProperty.call(edge, 'branch')) return undefined;
  const raw = (edge as any).branch;
  if (raw === null || raw === undefined) return undefined;
  return String(raw);
};

const isScheduleVisualActive = (
  nodeType: string,
  config: Record<string, any> | undefined,
  workflowPublished: boolean,
): boolean => {
  if (nodeType !== 'schedule_trigger') return false;
  return Boolean(workflowPublished) && parseBooleanLike(config?.enabled, true);
};

const isNodeActive = (rawValue: unknown): boolean => parseBooleanLike(rawValue, true);

type SwitchBranchLookup = {
  caseIds: Set<string>;
  labelToId: Map<string, string>;
  defaultCase: string;
};

const normalizeSwitchNodeConfig = (config: Record<string, any> | undefined): Record<string, any> => {
  const safeConfig = config && typeof config === 'object' ? config : {};
  const nextConfig = { ...safeConfig };
  const rawCases = Array.isArray(nextConfig.cases) ? nextConfig.cases : [];
  nextConfig.cases = rawCases
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any, index: number) => {
      const id = String(item.id || item.label || `case_${index + 1}`).trim();
      return {
        ...item,
        id,
        label: String(item.label || '').trim(),
      };
    });
  const defaultCase = String(nextConfig.default_case || 'default').trim();
  nextConfig.default_case = defaultCase || 'default';
  return nextConfig;
};

const MERGE_MODE_ALIASES: Record<string, string> = {
  choose_input1: 'choose_input_1',
  choose_input_1: 'choose_input_1',
  choose_input2: 'choose_input_2',
  choose_input_2: 'choose_input_2',
  choose_input: 'choose_branch',
  choose: 'choose_branch',
  passthrough: 'choose_input_1',
  pass_through: 'choose_input_1',
  'pass-through': 'choose_input_1',
  pass: 'choose_input_1',
};
const MERGE_JOIN_TYPES = new Set(['inner', 'left', 'right', 'outer']);
const MERGE_OUTPUT_MODES = new Set(['append', 'combine_by_position', 'combine_by_fields']);
const MERGE_KNOWN_CONFIG_KEYS = new Set([
  'mode',
  'input_count',
  'choose_branch',
  'output_key',
  'input_1_handle',
  'input_2_handle',
  'join_type',
  'input_1_field',
  'input_2_field',
  'allow_missing_branch_fallback',
]);
const MERGE_EDITOR_DEFAULT_CONFIG: Record<string, any> = (() => {
  const mergeNodeDefinition = NODE_LIBRARY.transform.find((node) => node.type === 'merge');
  return { ...(mergeNodeDefinition?.default_config || {}) };
})();

const normalizeMergeMode = (rawMode: unknown): string => {
  const normalized = String(rawMode || 'append').trim().toLowerCase();
  if (!normalized) return 'append';
  return MERGE_MODE_ALIASES[normalized] || normalized;
};

const normalizeMergeInputCount = (rawCount: unknown): number => {
  const parsed = Number.parseInt(String(rawCount ?? ''), 10);
  if (!Number.isFinite(parsed)) return 2;
  return Math.min(6, Math.max(2, parsed));
};

const normalizeMergeConfigForEditor = (config: Record<string, any> | undefined): Record<string, any> => {
  const safeConfig = config && typeof config === 'object' ? config : {};
  const nextConfig = {
    ...MERGE_EDITOR_DEFAULT_CONFIG,
    ...safeConfig,
  };
  const mode = normalizeMergeMode(nextConfig.mode);
  const inputCount = normalizeMergeInputCount(nextConfig.input_count);
  const chooseBranchRaw = String(nextConfig.choose_branch || '').trim().toLowerCase();
  const chooseBranch = chooseBranchRaw || (mode === 'choose_input_2' ? 'input2' : 'input1');
  nextConfig.mode = mode;
  nextConfig.input_count = inputCount;
  nextConfig.choose_branch = chooseBranch;
  return nextConfig;
};

const pruneMergeConfigForPersistence = (config: Record<string, any> | undefined): Record<string, any> => {
  const editorConfig = normalizeMergeConfigForEditor(config);
  const mode = normalizeMergeMode(editorConfig.mode);
  const inputCount = normalizeMergeInputCount(editorConfig.input_count);
  const chooseBranch = String(editorConfig.choose_branch || 'input1').trim().toLowerCase() || 'input1';
  const outputKey = String(editorConfig.output_key || '').trim() || 'merged';
  const input1Handle = String(editorConfig.input_1_handle || 'input1').trim() || 'input1';
  const input2Handle = String(editorConfig.input_2_handle || 'input2').trim() || 'input2';
  const joinTypeRaw = String(editorConfig.join_type || 'inner').trim().toLowerCase();
  const joinType = MERGE_JOIN_TYPES.has(joinTypeRaw) ? joinTypeRaw : 'inner';
  const nextConfig: Record<string, any> = Object.fromEntries(
    Object.entries(editorConfig).filter(([key]) => !MERGE_KNOWN_CONFIG_KEYS.has(key)),
  );

  nextConfig.mode = mode;
  nextConfig.input_count = inputCount;
  if (parseBooleanLike(editorConfig.allow_missing_branch_fallback, false)) {
    nextConfig.allow_missing_branch_fallback = true;
  }

  if (mode === 'choose_branch') {
    nextConfig.choose_branch = chooseBranch;
    return nextConfig;
  }

  if (mode === 'choose_input_1') {
    nextConfig.input_1_handle = input1Handle;
    return nextConfig;
  }

  if (mode === 'choose_input_2') {
    nextConfig.input_2_handle = input2Handle;
    return nextConfig;
  }

  if (MERGE_OUTPUT_MODES.has(mode)) {
    nextConfig.output_key = outputKey;
  }

  if (mode === 'combine_by_position' || mode === 'combine_by_fields') {
    nextConfig.join_type = joinType;
    nextConfig.input_1_handle = input1Handle;
    nextConfig.input_2_handle = input2Handle;
  }
  if (mode === 'combine_by_fields') {
    nextConfig.input_1_field = String(editorConfig.input_1_field || '').trim();
    nextConfig.input_2_field = String(editorConfig.input_2_field || '').trim();
  }

  return nextConfig;
};

const buildSwitchBranchLookup = (nodes: any[]): Map<string, SwitchBranchLookup> => {
  const lookup = new Map<string, SwitchBranchLookup>();

  for (const node of nodes || []) {
    if (node?.type !== 'switch') continue;

    const config = normalizeSwitchNodeConfig(node?.config || {});
    const labelToId = new Map<string, string>();
    const caseIds = new Set<string>();

    for (const rawCase of config.cases || []) {
      const caseId = String(rawCase?.id || '').trim();
      const caseLabel = String(rawCase?.label || '').trim();
      if (caseId) {
        caseIds.add(caseId);
      }
      if (caseId && caseLabel) {
        labelToId.set(caseLabel, caseId);
      }
    }

    lookup.set(String(node.id), {
      caseIds,
      labelToId,
      defaultCase: String(config.default_case || 'default'),
    });
  }

  return lookup;
};

const normalizeSwitchEdgeBranch = (
  rawBranch: string | null | undefined,
  branchLookup: SwitchBranchLookup | undefined,
): string | null => {
  const branch = String(rawBranch || '').trim();
  if (!branch) return null;
  if (!branchLookup) return branch;
  if (branchLookup.caseIds.has(branch) || branch === branchLookup.defaultCase) {
    return branch;
  }
  return branchLookup.labelToId.get(branch) || branch;
};

const buildFormPageUrl = (workflowId: string, nodeId: string): string => {
  const origin = window.location.origin.replace(/\/$/, '');
  return `${origin}/app/forms/${workflowId}?nodeId=${nodeId}`;
};

const initialNodes: WorkflowNode[] = [];
const initialEdges: WorkflowEdge[] = [];

interface ExecutionHistoryEntry {
  executionId: string;
  status: string;
  triggeredBy: string;
  startedAt: string | null;
  finishedAt: string | null;
  errorMessage: string | null;
  durationMs?: number;
}

interface CanvasHistoryEntry {
  definition: {
    nodes: Array<{
      id: string;
      type: string;
      label: string;
      position: XYPosition;
      config: Record<string, any>;
    }>;
    edges: Array<{
      id: string;
      source: string;
      target: string;
      sourceHandle?: string | null;
      targetHandle?: string | null;
      branch?: string;
    }>;
    loop_control?: {
      enabled?: boolean;
      max_node_executions?: number;
      max_total_node_executions?: number;
    };
  };
  signature: string;
}

interface AiPreviewGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  name: string;
}

interface WorkflowClipboardNode {
  id: string;
  type: WorkflowNode['type'];
  position: XYPosition;
  data: Omit<WorkflowNodeData, 'onToggleActive'>;
}

interface WorkflowClipboardEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  branch?: string;
  type?: string;
  animated?: boolean;
  style?: Record<string, any>;
  markerEnd?: any;
}

interface WorkflowClipboardPayload {
  version: number;
  sourceWorkflowId: string;
  copiedAtMs: number;
  nodes: WorkflowClipboardNode[];
  edges: WorkflowClipboardEdge[];
}

interface CanvasContextMenuState {
  x: number;
  y: number;
  flowPosition: XYPosition;
  nodeId: string | null;
  alignRight: boolean;
  alignBottom: boolean;
}

interface WorkflowVersionDetail extends WorkflowVersion {
  snapshot_json: {
    name: string;
    description?: string | null;
    definition: {
      nodes: any[];
      edges: any[];
      loop_control?: {
        enabled?: boolean;
        max_node_executions?: number;
        max_total_node_executions?: number;
      };
    };
  };
}

const isWorkflowClipboardPayload = (value: any): value is WorkflowClipboardPayload => {
  if (!value || typeof value !== 'object') return false;
  if (value.version !== WORKFLOW_CLIPBOARD_VERSION) return false;
  if (typeof value.sourceWorkflowId !== 'string') return false;
  if (!Array.isArray(value.nodes) || !Array.isArray(value.edges)) return false;
  return value.nodes.every((node: any) => (
    node
    && typeof node === 'object'
    && typeof node.id === 'string'
    && node.position
    && Number.isFinite(Number(node.position.x))
    && Number.isFinite(Number(node.position.y))
    && node.data
    && typeof node.data === 'object'
  ));
};

const persistWorkflowClipboard = (payload: WorkflowClipboardPayload) => {
  try {
    window.localStorage.setItem(WORKFLOW_CLIPBOARD_STORAGE_KEY, JSON.stringify(payload));
  } catch (_error) {
    // Ignore storage write failures (private mode / quota / unavailable storage).
  }
};

const readWorkflowClipboardFromStorage = (): WorkflowClipboardPayload | null => {
  try {
    const raw = window.localStorage.getItem(WORKFLOW_CLIPBOARD_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isWorkflowClipboardPayload(parsed) ? parsed : null;
  } catch (_error) {
    return null;
  }
};

interface WorkflowCanvasProps {
  workflowId: string;
  isPollingEnabled?: boolean;
  onTogglePollingEnabled?: () => void;
  isPublished?: boolean;
  footerOffset?: number;
  ensureWorkflowSaved?: () => Promise<boolean> | boolean;
  onExecutionStart?: (executionId: string) => void;
  onExecutionUpdate?: (detail: ExecutionDetail) => void;
  onToggleAiAssistant?: () => void;
  isAiAssistantOpen?: boolean;
  onCanvasMutated?: (reason: string) => void;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  workflowId,
  isPollingEnabled = true,
  onTogglePollingEnabled,
  isPublished = false,
  footerOffset = 0,
  ensureWorkflowSaved,
  onExecutionStart,
  onExecutionUpdate,
  onToggleAiAssistant,
  isAiAssistantOpen,
  onCanvasMutated,
}) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const connectingNode = useRef<{
    nodeId: string;
    handleId: string | null;
    connectionType: 'source' | 'target';
  } | null>(null);
  const edgeQuickAddTarget = useRef<{
    edgeId: string;
    source: string;
    target: string;
    sourceHandle: string | null;
    targetHandle: string | null;
  } | null>(null);
  const [nodes, setNodes, onNodesChangeBase] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<WorkflowEdge>(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const { isDark } = useTheme();
  const [activeTab, setActiveTab] = useState<'editor' | 'executions' | 'versions'>('editor');
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistoryEntry[]>([]);
  const [workflowVersions, setWorkflowVersions] = useState<WorkflowVersion[]>([]);
  const [isVersionsLoading, setIsVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedVersionDetail, setSelectedVersionDetail] = useState<WorkflowVersionDetail | null>(null);
  const [isVersionDetailLoading, setIsVersionDetailLoading] = useState(false);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [versionPreviewMeta, setVersionPreviewMeta] = useState<{
    versionId: string;
    versionNumber: number;
  } | null>(null);
  const executionHistoryRef = useRef<ExecutionHistoryEntry[]>([]);
  const versionPreviewBaseDefinitionRef = useRef<CanvasHistoryEntry['definition'] | null>(null);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [selectedExecutionDetail, setSelectedExecutionDetail] = useState<ExecutionDetail | null>(null);
  const [isExecutionDetailLoading, setIsExecutionDetailLoading] = useState(false);
  const [executionDetailError, setExecutionDetailError] = useState<string | null>(null);
  const isHydratingCanvasRef = useRef(false);
  const isApplyingHistoryRef = useRef(false);
  const executionDetailCacheRef = useRef<Record<string, ExecutionDetail>>({});
  const latestSyncedExecutionIdRef = useRef<string | null>(null);
  const externalExecutionToastShownRef = useRef<Set<string>>(new Set());
  const executionDetailRequestIdRef = useRef(0);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const historyStackRef = useRef<CanvasHistoryEntry[]>([]);
  const historyIndexRef = useRef(-1);
  const historyCommitTimeoutRef = useRef<number | null>(null);
  const aiApplyTimeoutRef = useRef<number | null>(null);
  const aiHighlightTimeoutRef = useRef<number | null>(null);
  const clipboardHighlightTimeoutRef = useRef<number | null>(null);
  const lastPointerFlowPositionRef = useRef<XYPosition | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [isAiApplyingChanges, setIsAiApplyingChanges] = useState(false);
  const [recentAiNodeIds, setRecentAiNodeIds] = useState<string[]>([]);
  const [recentAiEdgeIds, setRecentAiEdgeIds] = useState<string[]>([]);
  const [recentClipboardNodeIds, setRecentClipboardNodeIds] = useState<string[]>([]);
  const [recentClipboardEdgeIds, setRecentClipboardEdgeIds] = useState<string[]>([]);
  const [contextMenuState, setContextMenuState] = useState<CanvasContextMenuState | null>(null);
  const [hasClipboardData, setHasClipboardData] = useState<boolean>(() => Boolean(readWorkflowClipboardFromStorage()));
  const workflowClipboardRef = useRef<WorkflowClipboardPayload | null>(null);
  const clipboardPasteCountRef = useRef(0);
  const workflowLoopControlRef = useRef<Record<string, any>>({ ...DEFAULT_LOOP_CONTROL });
  const isReadOnly = isPublished;

  const notifyReadOnlyEdit = useCallback(() => {
    toast.error(PUBLISHED_WORKFLOW_EDIT_MESSAGE);
  }, []);

  const buildWorkflowDefinition = useCallback((sourceNodes: WorkflowNode[], sourceEdges: WorkflowEdge[]) => {
    return {
      nodes: sourceNodes.map((node) => ({
        // Never persist inline Telegram secrets in workflow JSON.
        // Telegram bot token + chat ID must come from saved credentials.
        config: (() => {
          const nextConfig = { ...(node.data.config || {}) };
          if (node.data.type === 'telegram') {
            delete nextConfig.bot_token;
            delete nextConfig.chat_id;
          }
          if (
            node.data.type === 'get_gmail_message' ||
            node.data.type === 'send_gmail_message' ||
            node.data.type === 'create_gmail_draft' ||
            node.data.type === 'add_gmail_label'
          ) {
            delete nextConfig.app_password;
            delete nextConfig.password;
            delete nextConfig.api_key;
            delete nextConfig.email;
            delete nextConfig.user_email;
            delete nextConfig.username;
          }
          if (node.data.type === 'create_google_sheets' || node.data.type === 'search_update_google_sheets') {
            delete nextConfig.service_account_json;
            delete nextConfig.serviceAccountJson;
            delete nextConfig.private_key;
            delete nextConfig.privateKey;
          }
          if (node.data.type === 'create_google_docs' || node.data.type === 'read_google_docs' || node.data.type === 'update_google_docs') {
            delete nextConfig.service_account_json;
            delete nextConfig.serviceAccountJson;
            delete nextConfig.private_key;
            delete nextConfig.privateKey;
          }
          if (node.data.type === 'slack_send_message') {
            delete nextConfig.webhook_url;
            delete nextConfig.channel;
          }
          if (node.data.type === 'switch') {
            return stripConfigEditorMetadata(normalizeSwitchNodeConfig(nextConfig));
          }
          if (node.data.type === 'if_else') {
            return stripConfigEditorMetadata(normalizeIfElseNodeConfig(nextConfig));
          }
          if (node.data.type === 'merge') {
            return stripConfigEditorMetadata(pruneMergeConfigForPersistence(nextConfig));
          }
          return stripConfigEditorMetadata(nextConfig);
        })(),
        id: node.id,
        type: node.data.type,
        label: node.data.label,
        position: node.position,
        is_active: isNodeActive(node.data.is_active),
      })),
      edges: sourceEdges.map((edge: any) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle,
        targetHandle: edge.targetHandle,
        branch: edge.sourceHandle ?? edge.branch ?? undefined,
      })),
      loop_control: {
        ...DEFAULT_LOOP_CONTROL,
        ...(workflowLoopControlRef.current || {}),
      },
    };
  }, []);

  const getCurrentHistoryEntry = useCallback((): CanvasHistoryEntry => {
    const definition = buildWorkflowDefinition(nodesRef.current, edgesRef.current);
    return {
      definition,
      signature: JSON.stringify(definition),
    };
  }, [buildWorkflowDefinition]);

  const updateUndoRedoAvailability = useCallback(() => {
    const index = historyIndexRef.current;
    const stackLength = historyStackRef.current.length;
    setCanUndo(index > 0);
    setCanRedo(index >= 0 && index < stackLength - 1);
  }, []);

  const clearPendingHistoryCommit = useCallback(() => {
    if (historyCommitTimeoutRef.current !== null) {
      window.clearTimeout(historyCommitTimeoutRef.current);
      historyCommitTimeoutRef.current = null;
    }
  }, []);

  const clearAiApplyTimers = useCallback(() => {
    if (aiApplyTimeoutRef.current !== null) {
      window.clearTimeout(aiApplyTimeoutRef.current);
      aiApplyTimeoutRef.current = null;
    }
    if (aiHighlightTimeoutRef.current !== null) {
      window.clearTimeout(aiHighlightTimeoutRef.current);
      aiHighlightTimeoutRef.current = null;
    }
  }, []);

  const clearClipboardHighlightTimer = useCallback(() => {
    if (clipboardHighlightTimeoutRef.current !== null) {
      window.clearTimeout(clipboardHighlightTimeoutRef.current);
      clipboardHighlightTimeoutRef.current = null;
    }
  }, []);

  const triggerAiApplyFeedback = useCallback((nodeIds: string[], edgeIds: string[]) => {
    clearAiApplyTimers();
    setIsAiApplyingChanges(true);
    setRecentAiNodeIds(nodeIds);
    setRecentAiEdgeIds(edgeIds);

    aiApplyTimeoutRef.current = window.setTimeout(() => {
      setIsAiApplyingChanges(false);
      aiApplyTimeoutRef.current = null;
    }, AI_APPLY_PROCESS_MS);

    aiHighlightTimeoutRef.current = window.setTimeout(() => {
      setRecentAiNodeIds([]);
      setRecentAiEdgeIds([]);
      aiHighlightTimeoutRef.current = null;
    }, AI_APPLY_PROCESS_MS + AI_APPLY_HIGHLIGHT_MS);
  }, [clearAiApplyTimers]);

  const triggerClipboardMutationFeedback = useCallback((nodeIds: string[], edgeIds: string[]) => {
    clearClipboardHighlightTimer();
    setRecentClipboardNodeIds(nodeIds);
    setRecentClipboardEdgeIds(edgeIds);
    clipboardHighlightTimeoutRef.current = window.setTimeout(() => {
      setRecentClipboardNodeIds([]);
      setRecentClipboardEdgeIds([]);
      clipboardHighlightTimeoutRef.current = null;
    }, 1700);
  }, [clearClipboardHighlightTimer]);

  const resetUndoRedoHistory = useCallback((definition?: CanvasHistoryEntry['definition']) => {
    const nextDefinition = definition || buildWorkflowDefinition(nodesRef.current, edgesRef.current);
    historyStackRef.current = [{
      definition: nextDefinition,
      signature: JSON.stringify(nextDefinition),
    }];
    historyIndexRef.current = 0;
    updateUndoRedoAvailability();
  }, [buildWorkflowDefinition, updateUndoRedoAvailability]);

  const commitHistorySnapshot = useCallback(() => {
    if (isHydratingCanvasRef.current || isApplyingHistoryRef.current) {
      return;
    }

    const nextEntry = getCurrentHistoryEntry();
    const currentEntry = historyStackRef.current[historyIndexRef.current];

    if (currentEntry?.signature === nextEntry.signature) {
      return;
    }

    const nextStack = historyStackRef.current.slice(0, historyIndexRef.current + 1);
    nextStack.push(nextEntry);

    if (nextStack.length > UNDO_REDO_HISTORY_LIMIT) {
      nextStack.shift();
    }

    historyStackRef.current = nextStack;
    historyIndexRef.current = nextStack.length - 1;
    updateUndoRedoAvailability();
  }, [getCurrentHistoryEntry, updateUndoRedoAvailability]);

  const scheduleHistorySnapshot = useCallback(() => {
    clearPendingHistoryCommit();
    historyCommitTimeoutRef.current = window.setTimeout(() => {
      historyCommitTimeoutRef.current = null;
      commitHistorySnapshot();
    }, UNDO_REDO_COMMIT_DEBOUNCE_MS);
  }, [clearPendingHistoryCommit, commitHistorySnapshot]);

  const flushPendingHistoryCommit = useCallback(() => {
    if (historyCommitTimeoutRef.current !== null) {
      window.clearTimeout(historyCommitTimeoutRef.current);
      historyCommitTimeoutRef.current = null;
      commitHistorySnapshot();
    }
  }, [commitHistorySnapshot]);

  const formatDateTime = (iso: string | null) => {
    return formatDateTimeInAppTimezone(iso);
  };

  const getStatusBadgeClasses = (status: string) => {
    const normalized = String(status || '').toUpperCase();
    if (normalized === 'SUCCEEDED') {
      return 'bg-emerald-100/80 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/20';
    }
    if (normalized === 'FAILED') {
      return 'bg-rose-100/80 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border border-rose-200/50 dark:border-rose-500/20';
    }
    if (normalized === 'RUNNING' || normalized === 'QUEUED' || normalized === 'WAITING') {
      return 'bg-purple-100/80 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400 border border-purple-200/50 dark:border-purple-500/20';
    }
    return 'bg-slate-100/80 text-slate-700 dark:bg-slate-500/20 dark:text-slate-400 border border-slate-200/50 dark:border-slate-500/20';
  };

  useEffect(() => {
    executionHistoryRef.current = executionHistory;
  }, [executionHistory]);

  const toExecutionHistoryEntry = useCallback((exe: any): ExecutionHistoryEntry => {
    const executionId = String(exe?.executionId ?? exe?.id ?? '');
    return {
      executionId,
      status: String(exe?.status || 'PENDING').toUpperCase(),
      triggeredBy: String(exe?.triggeredBy ?? exe?.triggered_by ?? 'manual'),
      startedAt: exe?.startedAt ?? exe?.started_at ?? null,
      finishedAt: exe?.finishedAt ?? exe?.finished_at ?? null,
      errorMessage: (exe?.errorMessage ?? exe?.error_message)
        ? toUserFriendlyErrorMessage(exe?.errorMessage ?? exe?.error_message, '')
        : null,
      durationMs:
        (exe?.startedAt ?? exe?.started_at) && (exe?.finishedAt ?? exe?.finished_at)
          ? Date.parse(exe?.finishedAt ?? exe?.finished_at) - Date.parse(exe?.startedAt ?? exe?.started_at)
          : undefined,
    };
  }, []);

  const upsertExecutionHistoryEntry = useCallback((entry: ExecutionHistoryEntry) => {
    if (!entry.executionId) return;
    setExecutionHistory((history) => {
      const index = history.findIndex((item) => item.executionId === entry.executionId);
      if (index === -1) {
        return [entry, ...history];
      }
      const next = [...history];
      next[index] = { ...next[index], ...entry };
      return next;
    });
  }, []);

  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [nodes, edges]);

  useEffect(() => {
    clearPendingHistoryCommit();
    clearAiApplyTimers();
    clearClipboardHighlightTimer();
    historyStackRef.current = [];
    historyIndexRef.current = -1;
    setCanUndo(false);
    setCanRedo(false);
    setIsAiApplyingChanges(false);
    setRecentAiNodeIds([]);
    setRecentAiEdgeIds([]);
    setRecentClipboardNodeIds([]);
    setRecentClipboardEdgeIds([]);
    setAiPreviewGraph(null);
    setSelectedExecutionId(null);
    setSelectedExecutionDetail(null);
    setExecutionDetailError(null);
    setIsExecutionDetailLoading(false);
    executionDetailCacheRef.current = {};
    latestSyncedExecutionIdRef.current = null;
    externalExecutionToastShownRef.current = new Set();
    executionDetailRequestIdRef.current = 0;
    setHasPickedNewWorkflowStarter(false);
    setShowRunFlowSelector(false);
    setRunFlowOptions([]);
    setIsStartingSelectedFlow(false);
    workflowLoopControlRef.current = { ...DEFAULT_LOOP_CONTROL };
    workflowClipboardRef.current = readWorkflowClipboardFromStorage();
    setHasClipboardData(Boolean(workflowClipboardRef.current));
    clipboardPasteCountRef.current = 0;
    setContextMenuState(null);
    lastPointerFlowPositionRef.current = null;
  }, [workflowId, clearPendingHistoryCommit, clearAiApplyTimers, clearClipboardHighlightTimer]);

  useEffect(() => {
    if (workflowId === 'new') {
      setExecutionHistory([]);
      return;
    }
    if (!isPollingEnabled) {
      return;
    }

    let cancelled = false;
    const fetchExecutions = async () => {
      try {
        const response = await executionService.listExecutions(workflowId);
        if (response && response.executions) {
          if (cancelled) return;
          const formattedHistory = response.executions.map((exe: any) => toExecutionHistoryEntry(exe));
          setExecutionHistory(formattedHistory);
        }
      } catch (error) {
        console.error('Failed to fetch execution history:', error);
      }
    };

    void fetchExecutions();
    const intervalId = window.setInterval(() => {
      void fetchExecutions();
    }, EXTERNAL_EXECUTION_SYNC_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isPollingEnabled, toExecutionHistoryEntry, workflowId]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key && event.key !== WORKFLOW_CLIPBOARD_STORAGE_KEY) return;
      const payload = readWorkflowClipboardFromStorage();
      workflowClipboardRef.current = payload;
      setHasClipboardData(Boolean(payload));
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.data.type !== 'schedule_trigger') return node;
        const scheduleIsActive = isScheduleVisualActive(
          node.data.type,
          node.data.config,
          isPublished,
        );
        if (node.data.schedule_is_active === scheduleIsActive) {
          return node;
        }
        return {
          ...node,
          data: {
            ...node.data,
            schedule_is_active: scheduleIsActive,
          },
        };
      }),
    );
  }, [isPublished, setNodes]);

  const applyExecutionDetailToCanvas = useCallback((detail: ExecutionDetail) => {
    const nodeResultById = new Map(detail.node_results.map((nodeResult) => [nodeResult.node_id, nodeResult]));
    setNodes((nds) =>
      nds.map((node) => {
        const nodeResult = nodeResultById.get(node.id);
        if (!nodeResult) {
          return {
            ...node,
            data: {
              ...node.data,
              status: 'PENDING',
              last_execution_result: null,
            },
          };
        }
        return {
          ...node,
          data: {
            ...node.data,
            status: nodeResult.status,
            last_execution_result: nodeResult,
            last_output: nodeResult.output_data ?? node.data.last_output,
          },
        };
      }),
    );
  }, [setNodes]);

  const inspectExecution = useCallback(async (executionId: string) => {
    setSelectedExecutionId(executionId);
    setExecutionDetailError(null);
    setSelectedExecutionDetail(null);

    const cached = executionDetailCacheRef.current[executionId];
    if (cached) {
      setSelectedExecutionDetail(cached);
      applyExecutionDetailToCanvas(cached);
      setIsExecutionDetailLoading(false);
      return;
    }

    const requestId = executionDetailRequestIdRef.current + 1;
    executionDetailRequestIdRef.current = requestId;
    setIsExecutionDetailLoading(true);

    try {
      const detail = await executionService.getExecution(executionId);
      if (executionDetailRequestIdRef.current !== requestId) return;

      executionDetailCacheRef.current[executionId] = detail;
      setSelectedExecutionDetail(detail);
      applyExecutionDetailToCanvas(detail);
    } catch (error: any) {
      if (executionDetailRequestIdRef.current !== requestId) return;
      const message = toUserFriendlyErrorMessage(
        error?.response?.data?.detail,
        'Failed to load execution detail',
      );
      setExecutionDetailError(message);
      toast.error(message);
    } finally {
      if (executionDetailRequestIdRef.current === requestId) {
        setIsExecutionDetailLoading(false);
      }
    }
  }, [applyExecutionDetailToCanvas]);

  const handleExecutionRowClick = useCallback((executionId: string) => {
    if (selectedExecutionId === executionId) {
      executionDetailRequestIdRef.current += 1;
      setSelectedExecutionId(null);
      setSelectedExecutionDetail(null);
      setExecutionDetailError(null);
      setIsExecutionDetailLoading(false);
      return;
    }

    void inspectExecution(executionId);
  }, [inspectExecution, selectedExecutionId]);

  // Quick Add State
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState<XYPosition | null>(null);
  const [menuSearchTerm, setMenuSearchTerm] = useState('');
  const [hasPickedNewWorkflowStarter, setHasPickedNewWorkflowStarter] = useState(false);
  const menuSearchRef = useRef<HTMLInputElement>(null);

  // Config Panel State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [aiPreviewGraph, setAiPreviewGraph] = useState<AiPreviewGraph | null>(null);
  const isAiPreviewMode = aiPreviewGraph !== null;
  const isVersionPreviewMode = versionPreviewMeta !== null;
  const isCanvasReadOnlyPreviewMode = isAiPreviewMode || isVersionPreviewMode;
  const previewEditBlockMessage = isAiPreviewMode
    ? 'Accept or discard the AI preview before editing.'
    : 'Exit version preview before editing.';

  // Alignment Detection
  const [isAligned, setIsAligned] = useState(true);

  // Execution State
  const pollingIntervalRef = useRef<number | null>(null);
  const activeExecutionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const handleQuickAdd = (e: any) => {
      if (isCanvasReadOnlyPreviewMode) {
        toast(previewEditBlockMessage, { icon: 'ℹ️' });
        return;
      }

      if (isReadOnly) {
        notifyReadOnlyEdit();
        return;
      }
      if (isAiPreviewMode) {
        toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
        return;
      }

      const {
        nodeId,
        handleId,
        connectionType = 'source',
        clientX,
        clientY,
      } = e.detail || {};
      const node = nodes.find(n => n.id === nodeId);
      if (!node || !reactFlowInstance) return;

      const position = (typeof clientX === 'number' && typeof clientY === 'number')
        ? reactFlowInstance.screenToFlowPosition({ x: clientX, y: clientY })
        : {
            x: connectionType === 'target' ? node.position.x : node.position.x + 250,
            y: connectionType === 'target' ? node.position.y + 160 : node.position.y,
          };

      connectingNode.current = { nodeId, handleId, connectionType };
      edgeQuickAddTarget.current = null;
      setMenuPosition(position);
      setMenuVisible(true);
    };

    const handleQuickAddEdge = (e: any) => {
      if (isCanvasReadOnlyPreviewMode) {
        toast(previewEditBlockMessage, { icon: 'ℹ️' });
        return;
      }

      if (isReadOnly) {
        notifyReadOnlyEdit();
        return;
      }
      if (isAiPreviewMode) {
        toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
        return;
      }

      const {
        edgeId,
        source,
        target,
        sourceHandle = null,
        targetHandle = null,
        clientX,
        clientY,
      } = e.detail || {};

      if (!edgeId || !source || !target || !reactFlowInstance) return;
      const edgeExists = edgesRef.current.some((edge) => edge.id === edgeId);
      if (!edgeExists) return;

      if (typeof clientX !== 'number' || typeof clientY !== 'number') return;
      const position = reactFlowInstance.screenToFlowPosition({ x: clientX, y: clientY });

      edgeQuickAddTarget.current = {
        edgeId,
        source,
        target,
        sourceHandle,
        targetHandle,
      };
      connectingNode.current = null;
      setMenuPosition(position);
      setMenuVisible(true);
    };

    window.addEventListener('rf-quick-add', handleQuickAdd);
    window.addEventListener('rf-quick-add-edge', handleQuickAddEdge);
    return () => {
      window.removeEventListener('rf-quick-add', handleQuickAdd);
      window.removeEventListener('rf-quick-add-edge', handleQuickAddEdge);
      setMenuSearchTerm('');
    };

  }, [isCanvasReadOnlyPreviewMode, nodes, previewEditBlockMessage, reactFlowInstance, isAiPreviewMode, isReadOnly, notifyReadOnlyEdit]);


  useEffect(() => {
    if (menuVisible && menuSearchRef.current) {
      setTimeout(() => menuSearchRef.current?.focus(), 50);
    } else if (!menuVisible) {
      setMenuSearchTerm('');
      connectingNode.current = null;
      edgeQuickAddTarget.current = null;
    }
  }, [menuVisible]);

  const [showTriggerForm, setShowTriggerForm] = useState(false);
  const [triggerFormData, setTriggerFormData] = useState<FormValues>({});
  const [triggerFormErrors, setTriggerFormErrors] = useState<FormErrors>({});
  const [triggerNode, setTriggerNode] = useState<WorkflowNode | null>(null);
  const [showRunFlowSelector, setShowRunFlowSelector] = useState(false);
  const [runFlowOptions, setRunFlowOptions] = useState<WorkflowNode[]>([]);
  const [isStartingSelectedFlow, setIsStartingSelectedFlow] = useState(false);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isStoppingExecution, setIsStoppingExecution] = useState(false);

  const emitCanvasMutation = useCallback((reason: string) => {
    if (isHydratingCanvasRef.current || isApplyingHistoryRef.current) return;
    scheduleHistorySnapshot();
    onCanvasMutated?.(reason);
  }, [onCanvasMutated, scheduleHistorySnapshot]);

  const toggleNodeActive = useCallback((nodeId: string) => {

    if (isCanvasReadOnlyPreviewMode) {
      toast(previewEditBlockMessage, { icon: 'ℹ️' });
      return;
    }

    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    if (isAiPreviewMode) {
      toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
      return;
    }

    let changed = false;
    let nextActiveState = true;

    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== nodeId) return node;
        changed = true;
        nextActiveState = !isNodeActive(node.data.is_active);
        return {
          ...node,
          data: {
            ...node.data,
            is_active: nextActiveState,
            status: 'PENDING',
            last_execution_result: null,
          },
        };
      }),
    );

    if (!changed) return;
    emitCanvasMutation('node_active_toggle');
    toast.success(nextActiveState ? 'Node activated' : 'Node deactivated');

  }, [emitCanvasMutation, isCanvasReadOnlyPreviewMode, previewEditBlockMessage, setNodes, isAiPreviewMode, isReadOnly, notifyReadOnlyEdit,]);

  const onNodesChange = useCallback((changes: any[]) => {
    const hasReadOnlyMutation = changes.some((change) =>
      ['add', 'remove', 'reset', 'position'].includes(change?.type)
    );
    if (isReadOnly && hasReadOnlyMutation) {
      notifyReadOnlyEdit();
      return;
    }

    onNodesChangeBase(changes);

    if (isHydratingCanvasRef.current) return;
    const hasMeaningfulChange = changes.some((change) => {
      if (['add', 'remove', 'reset'].includes(change?.type)) {
        return true;
      }
      if (change?.type === 'position') {
        return change?.dragging !== true;
      }
      return false;
    });
    if (hasMeaningfulChange) {
      emitCanvasMutation('nodes_change');
    }
  }, [emitCanvasMutation, isReadOnly, notifyReadOnlyEdit, onNodesChangeBase]);

  const onEdgesChange = useCallback((changes: any[]) => {
    const hasReadOnlyMutation = changes.some((change) =>
      ['add', 'remove', 'reset'].includes(change?.type)
    );
    if (isReadOnly && hasReadOnlyMutation) {
      notifyReadOnlyEdit();
      return;
    }

    onEdgesChangeBase(changes);

    if (isHydratingCanvasRef.current) return;
    const hasMeaningfulChange = changes.some((change) =>
      ['add', 'remove', 'reset'].includes(change?.type)
    );
    if (hasMeaningfulChange) {
      emitCanvasMutation('edges_change');
    }
  }, [emitCanvasMutation, isReadOnly, notifyReadOnlyEdit, onEdgesChangeBase]);

  useEffect(() => {
    const misaligned = nodes.some(
      (node) => node.position.x % 20 !== 0 || node.position.y % 20 !== 0
    );
    setIsAligned(!misaligned);
  }, [nodes]);

  // Update edges to show status animations path-aware
  useEffect(() => {
    if (!isPollingEnabled) {
      setEdges((eds) =>
        eds.map((edge) => ({
          ...edge,
          animated: false,
          data: { ...edge.data, isActivePath: false, executionState: 'idle' },
        } as any)),
      );
      return;
    }

    const nodeById = new Map(nodes.map((node) => [node.id, node]));

    const isEdgeOnSelectedBranch = (edge: any, sourceNode: WorkflowNode | undefined): boolean => {
      if (!sourceNode) return false;

      const sourceStatus = sourceNode.data.status;
      if (!['RUNNING', 'WAITING', 'QUEUED', 'SUCCEEDED'].includes(String(sourceStatus || '').toUpperCase())) {
        return false;
      }

      if (['RUNNING', 'WAITING', 'QUEUED'].includes(String(sourceStatus || '').toUpperCase())) {
        return true;
      }

      const output = sourceNode.data.last_execution_result?.output_data;
      const chosenBranch = output?._branch;
      const isBranchingNode = ['if_else', 'switch'].includes(sourceNode.data.type || '');

      if (!isBranchingNode) {
        return true;
      }

      if (chosenBranch === undefined || chosenBranch === null) {
        return false;
      }

      const edgeBranch = edge.branch ?? edge.sourceHandle;
      return String(edgeBranch) === String(chosenBranch);
    };

    setEdges((eds) =>
      eds.map((edge) => {
        const sourceNode = nodeById.get(edge.source);
        const targetNode = nodeById.get(edge.target);
        const isOnSelectedPath = isEdgeOnSelectedBranch(edge, sourceNode as WorkflowNode | undefined);
        const targetFailed = targetNode?.data.status === 'FAILED';

        let executionState: 'idle' | 'running' | 'success' | 'failed' = 'idle';
        let shouldAnimate = false;
        let isActivePath = false;

        if (isOnSelectedPath && targetFailed) {
          executionState = 'failed';
          shouldAnimate = true;
          isActivePath = true;
        } else if (['RUNNING', 'WAITING', 'QUEUED'].includes(String(sourceNode?.data.status || '').toUpperCase()) && isOnSelectedPath) {
          executionState = 'running';
          shouldAnimate = true;
          isActivePath = true;
        } else if (sourceNode?.data.status === 'SUCCEEDED' && isOnSelectedPath) {
          executionState = 'success';
          shouldAnimate = true;
          isActivePath = true;
        }

        return {
          ...edge,
          animated: shouldAnimate,
          data: { ...edge.data, isActivePath, executionState },
        } as any;
      })
    );
  }, [isPollingEnabled, nodes, setEdges]);

  const autoLayout = useCallback((nodesToLayout: any[], edgesToLayout: any[]) => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    
    // Config layout: Left to Right
    dagreGraph.setGraph({ 
      rankdir: 'LR', 
      nodesep: AUTO_LAYOUT_NODE_GAP, 
      ranksep: AUTO_LAYOUT_RANK_GAP,
      marginx: 50,
      marginy: 50
    });

    nodesToLayout.forEach((node) => {
      dagreGraph.setNode(node.id, { width: 250, height: 100 });
    });

    const nodeTypeById = new Map(
      nodesToLayout.map((node) => [node.id, node?.data?.type || node?.type]),
    );

    // Important: AI Agent sub-node links (chat_model/memory/tool) should not
    // affect the main DAG layout. We place those child nodes manually later.
    const layoutEdges = edgesToLayout.filter((edge) => {
      const handle = String(edge.targetHandle || '');
      const isAiSubnodeLink =
        AI_AGENT_CHILD_HANDLES.includes(handle as (typeof AI_AGENT_CHILD_HANDLES)[number]) &&
        nodeTypeById.get(edge.target) === 'ai_agent';
      return !isAiSubnodeLink;
    });

    layoutEdges.forEach((edge) => {
      dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    const positioned = nodesToLayout.map((node) => {
      const nodeWithPosition = dagreGraph.node(node.id);
      return {
        ...node,
        position: {
          x: nodeWithPosition.x - 125, // Center adjustment
          y: nodeWithPosition.y - 50,
        },
      };
    });

    const positionedById = new Map(positioned.map((node) => [node.id, node]));
    const positionedNodeTypeById = new Map(
      positioned.map((node) => [node.id, node?.data?.type || node?.type]),
    );

    const aiChildLinks = edgesToLayout.filter((edge) => {
      const handle = String(edge.targetHandle || '');
      return (
        AI_AGENT_CHILD_HANDLES.includes(handle as (typeof AI_AGENT_CHILD_HANDLES)[number]) &&
        positionedNodeTypeById.get(edge.target) === 'ai_agent'
      );
    });

    const stackIndexByHandle = new Map<string, number>();

    aiChildLinks.forEach((edge) => {
      const parent = positionedById.get(edge.target);
      const child = positionedById.get(edge.source);
      if (!parent || !child) return;

      const handle = String(edge.targetHandle || 'memory');
      const key = `${edge.target}:${handle}`;
      const stackIndex = stackIndexByHandle.get(key) || 0;
      stackIndexByHandle.set(key, stackIndex + 1);

      const handleOffsetX = AI_AGENT_CHILD_X_OFFSET[handle] ?? 0;
      child.position = {
        x: parent.position.x + handleOffsetX,
        y: parent.position.y + AI_AGENT_CHILD_Y_OFFSET + stackIndex * AI_AGENT_CHILD_STACK_GAP,
      };
    });

    return positioned;
  }, []);

  const buildAiGraphFromDefinition = useCallback((definition: any): AiPreviewGraph => {
    const rawNodes = (definition?.nodes || []).map((n: any) => {
      const category = NODE_LIBRARY.trigger.some(ref => ref.type === n.type) ? 'trigger' :
        NODE_LIBRARY.action.some(ref => ref.type === n.type) ? 'action' :
          NODE_LIBRARY.transform.some(ref => ref.type === n.type) ? 'transform' :
            NODE_LIBRARY.input_output.some(ref => ref.type === n.type) ? 'input_output' : 'ai';
      return {
        ...n,
        data: {
          label: n.label || n.type,
          config: n.config || {},
          type: n.type,
          category,
          is_active: isNodeActive(n.is_active),
          onToggleActive: toggleNodeActive,
        },
      };
    });

    const positionedNodes = autoLayout(rawNodes, definition?.edges || []);

    const graphNodes: WorkflowNode[] = positionedNodes.map((n: any) => ({
      id: n.id,
      type: n.data.category,
      position: n.position,
      data: n.data,
    }));

    const usedEdgeIds = new Set<string>();
    const graphEdges: WorkflowEdge[] = (definition?.edges || []).map((e: any) => {
      const incomingId = typeof e?.id === 'string' ? e.id.trim() : '';
      const nextId = incomingId && incomingId.length <= 100 && !usedEdgeIds.has(incomingId)
        ? incomingId
        : generateUniqueEdgeId(usedEdgeIds);
      if (incomingId && incomingId.length <= 100 && !usedEdgeIds.has(incomingId)) {
        usedEdgeIds.add(incomingId);
      }
      return {
        ...e,
        id: nextId,
        type: 'deletable',
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
        style: { stroke: '#94a3b8', strokeWidth: 2 },
      };
    });

    return {
      nodes: graphNodes,
      edges: graphEdges,
      name: typeof definition?.name === 'string' ? definition.name : '',
    };
  }, [autoLayout, toggleNodeActive]);

  const applyAiGraphToCanvas = useCallback((graph: AiPreviewGraph) => {
    triggerAiApplyFeedback(
      graph.nodes.map((node) => node.id),
      graph.edges.map((edge) => edge.id),
    );
    setAiPreviewGraph(null);
    setSelectedNodeId(null);
    setNodes(graph.nodes);
    setEdges(graph.edges);
    emitCanvasMutation('apply_ai_workflow');

    window.setTimeout(() => {
      reactFlowInstance?.fitView({ duration: 800, padding: 0.2 });
    }, 100);
  }, [emitCanvasMutation, reactFlowInstance, triggerAiApplyFeedback]);

  const alignNodes = useCallback(() => {
    if (isCanvasReadOnlyPreviewMode) {
      toast(previewEditBlockMessage, { icon: 'ℹ️' });
      return;
    }
    const positionedNodes = autoLayout(nodes, edges);
    setNodes(positionedNodes);
    emitCanvasMutation('align_nodes');

    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ duration: 800, padding: 0.2 });
      }, 50);
    }

    toast.success('Workflow perfectly aligned');
  }, [isCanvasReadOnlyPreviewMode, nodes, edges, setNodes, autoLayout, reactFlowInstance, emitCanvasMutation, previewEditBlockMessage]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current !== null) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (isPollingEnabled) return;
    stopPolling();
  }, [isPollingEnabled, stopPolling]);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.data.workflow_execution_visual_active === isPollingEnabled) {
          return node;
        }
        return {
          ...node,
          data: {
            ...node.data,
            workflow_execution_visual_active: isPollingEnabled,
          },
        };
      }),
    );
  }, [isPollingEnabled, setNodes]);

  const computeUpstreamPrimePath = useCallback((targetNodeId: string) => {
    const incomingByTarget = new Map<string, WorkflowEdge[]>();
    edges.forEach((edge) => {
      const current = incomingByTarget.get(edge.target) || [];
      current.push(edge);
      incomingByTarget.set(edge.target, current);
    });

    const upstreamNodeIds = new Set<string>();
    const branchBySourceNodeId = new Map<string, string>();
    const stack: string[] = [targetNodeId];
    const seenTargets = new Set<string>();

    while (stack.length > 0) {
      const currentTarget = stack.pop() as string;
      if (seenTargets.has(currentTarget)) continue;
      seenTargets.add(currentTarget);

      const incomingEdges = incomingByTarget.get(currentTarget) || [];
      incomingEdges.forEach((edge) => {
        if (!edge.source || edge.source === currentTarget) return;
        upstreamNodeIds.add(edge.source);
        if (edge.sourceHandle) {
          branchBySourceNodeId.set(edge.source, edge.sourceHandle);
        }
        stack.push(edge.source);
      });
    }

    return { upstreamNodeIds, branchBySourceNodeId };
  }, [edges]);

  const pollExecution = useCallback(async (executionId: string) => {
    if (!isPollingEnabled) {
      return;
    }
    if (activeExecutionIdRef.current !== executionId) {
      return;
    }

    try {
      const detail = await executionService.getExecution(executionId);
      if (activeExecutionIdRef.current !== executionId) {
        return;
      }

      const normalizedExecutionStatus = String(detail.status || '').toUpperCase();
      const inProgress = ['RUNNING', 'PENDING', 'QUEUED', 'WAITING'].includes(normalizedExecutionStatus);

      // Update nodes with their execution status and results
      setNodes((nds) =>
        nds.map((node) => {
          const result = detail.node_results.find((r) => r.node_id === node.id);
          if (result) {
            // Keep optimistic "path already completed" highlighting while a
            // single-node execution is still in progress and upstream rows
            // are represented as PENDING by the backend.
            if (inProgress && result.status === 'PENDING' && node.data.status === 'SUCCEEDED') {
              return node;
            }

            return {
              ...node,
              data: {
                ...node.data,
                status: result.status,
                last_execution_result: result,
                last_output: result.output_data ?? node.data.last_output,
              }
            };
          }
          return node;
        })
      );
      upsertExecutionHistoryEntry(
        toExecutionHistoryEntry({
          id: detail.id,
          status: detail.status,
          triggered_by: detail.triggered_by,
          started_at: detail.started_at,
          finished_at: detail.finished_at,
          error_message: detail.error_message,
        }),
      );
      executionDetailCacheRef.current[executionId] = detail;
      if (selectedExecutionId === executionId) {
        setSelectedExecutionDetail(detail);
      }
      onExecutionUpdate?.(detail);

      if (detail.status === 'SUCCEEDED' || detail.status === 'FAILED') {
        stopPolling();
        activeExecutionIdRef.current = null;
        setActiveExecutionId(null);
        const triggerKind = String(detail.triggered_by || '').toLowerCase();
        const isWorkflowRun = ['manual', 'form', 'webhook', 'workflow'].includes(triggerKind);
        if (detail.status === 'SUCCEEDED') {
          toast.success(
            isWorkflowRun
              ? 'Workflow finished successfully'
              : 'Node execution finished successfully',
          );
        } else {
          const friendlyError = toUserFriendlyErrorMessage(
            detail.error_message,
            'Unknown error',
          );
          toast.error(
            isWorkflowRun
              ? `Workflow failed: ${friendlyError}`
              : `Node execution failed: ${friendlyError}`,
          );
        }
      }
    } catch (error) {
      console.error('Polling failed:', error);
      stopPolling();
    }
  }, [isPollingEnabled, onExecutionUpdate, selectedExecutionId, setNodes, stopPolling, toExecutionHistoryEntry, upsertExecutionHistoryEntry]);

  const beginExecutionTracking = useCallback((
    executionId: string,
    options?: { triggeredBy?: string; primeNodeId?: string },
  ) => {
    stopPolling();
    activeExecutionIdRef.current = executionId;
    setActiveExecutionId(executionId);
    onExecutionStart?.(executionId);

    if (options?.primeNodeId) {
      const { upstreamNodeIds, branchBySourceNodeId } = computeUpstreamPrimePath(options.primeNodeId);

      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === options.primeNodeId) {
            return {
              ...node,
              data: {
                ...node.data,
                status: 'RUNNING',
                last_execution_result: {
                  node_id: node.id,
                  node_type: node.data.type,
                  status: 'RUNNING',
                  input_data: null,
                  output_data: null,
                  error_message: null,
                  started_at: null,
                  finished_at: null,
                },
              },
            };
          }

          if (upstreamNodeIds.has(node.id)) {
            const branch = branchBySourceNodeId.get(node.id);
            return {
              ...node,
              data: {
                ...node.data,
                status: 'SUCCEEDED',
                last_execution_result: {
                  node_id: node.id,
                  node_type: node.data.type,
                  status: 'SUCCEEDED',
                  input_data: null,
                  output_data: branch ? { _branch: branch } : {},
                  error_message: null,
                  started_at: null,
                  finished_at: null,
                },
              },
            };
          }

          return {
            ...node,
            data: {
              ...node.data,
              status: 'PENDING',
              last_execution_result: null,
            },
          };
        }),
      );
    }

    setExecutionHistory((history) => [
      {
        executionId,
        status: 'PENDING',
        triggeredBy: options?.triggeredBy || 'manual',
        startedAt: null,
        finishedAt: null,
        errorMessage: null,
      },
      ...history,
    ]);
    if (!isPollingEnabled) {
      return;
    }
    void pollExecution(executionId);
    pollingIntervalRef.current = window.setInterval(() => {
      void pollExecution(executionId);
    }, EXECUTION_POLL_INTERVAL_MS);
  }, [computeUpstreamPrimePath, isPollingEnabled, onExecutionStart, pollExecution, setNodes, stopPolling]);

  useEffect(() => {
    const onFormExecutionStarted = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;

      const payload = event.data as {
        type?: string;
        workflowId?: string;
        executionId?: string;
        nodeId?: string;
      };

      if (!payload || payload.type !== FORM_EXECUTION_MESSAGE_TYPE) return;
      if (!payload.workflowId || payload.workflowId !== workflowId) return;
      if (!payload.executionId) return;

      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: { ...node.data, status: 'PENDING', last_execution_result: null },
        }))
      );
      beginExecutionTracking(payload.executionId, {
        triggeredBy: 'form',
        primeNodeId: payload.nodeId,
      });
      toast.success('Form submitted. Workflow execution started.');
    };

    window.addEventListener('message', onFormExecutionStarted);
    return () => window.removeEventListener('message', onFormExecutionStarted);
  }, [workflowId, beginExecutionTracking, setNodes]);

  const resetNodeExecutionVisualState = useCallback(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: { ...node.data, status: 'PENDING', last_execution_result: null },
      }))
    );
  }, [setNodes]);

  useEffect(() => {
    if (!isPollingEnabled) return;
    if (!workflowId || workflowId === 'new') return;
    const latestEntry = executionHistoryRef.current[0];
    if (!latestEntry?.executionId) return;

    let cancelled = false;
    const syncFromLatestHistory = async () => {
      const executionId = String(latestEntry.executionId || '');
      if (!executionId) return;

      if (activeExecutionIdRef.current === executionId) {
        return;
      }

      const latestStatus = String(latestEntry.status || '').toUpperCase();
      const isRunningExecution = ['RUNNING', 'PENDING', 'QUEUED', 'WAITING'].includes(latestStatus);

      if (isRunningExecution) {
        latestSyncedExecutionIdRef.current = executionId;
        resetNodeExecutionVisualState();
        beginExecutionTracking(executionId, {
          triggeredBy: latestEntry.triggeredBy || 'webhook',
        });
        if (!externalExecutionToastShownRef.current.has(executionId)) {
          externalExecutionToastShownRef.current.add(executionId);
          toast('Published URL run detected. Showing live status in editor.', { icon: 'ℹ️' });
        }
        return;
      }

      if (latestSyncedExecutionIdRef.current === executionId) {
        return;
      }

      try {
        const detail = executionDetailCacheRef.current[executionId]
          || await executionService.getExecution(executionId);
        if (cancelled || !detail) return;

        executionDetailCacheRef.current[executionId] = detail;
        latestSyncedExecutionIdRef.current = executionId;
        onExecutionStart?.(executionId);
        onExecutionUpdate?.(detail);
        applyExecutionDetailToCanvas(detail);
        if (selectedExecutionId === executionId) {
          setSelectedExecutionDetail(detail);
        }
      } catch (_error) {
        // Ignore transient lookup failures for historical rows.
      }
    };

    void syncFromLatestHistory();
    return () => {
      cancelled = true;
    };
  }, [
    applyExecutionDetailToCanvas,
    beginExecutionTracking,
    executionHistory,
    isPollingEnabled,
    onExecutionStart,
    onExecutionUpdate,
    resetNodeExecutionVisualState,
    selectedExecutionId,
    workflowId,
  ]);

  const hasRuntimeCycle = useCallback((): boolean => {
    const allNodes = nodesRef.current;
    const allEdges = edgesRef.current;
    const nodeIds = new Set(allNodes.map((node) => node.id));
    const nodeById = new Map(allNodes.map((node) => [node.id, node]));
    const adjacency = new Map<string, string[]>();

    nodeIds.forEach((nodeId) => adjacency.set(nodeId, []));
    allEdges.forEach((edge) => {
      const sourceNode = nodeById.get(edge.source);
      const targetNode = nodeById.get(edge.target);
      const isAiSubnodeLink =
        targetNode?.data?.type === 'ai_agent' &&
        (sourceNode?.data?.type === 'chat_model_openai' || sourceNode?.data?.type === 'chat_model_groq') &&
        AI_AGENT_CHILD_HANDLES.includes(String(edge.targetHandle || '') as (typeof AI_AGENT_CHILD_HANDLES)[number]);
      if (isAiSubnodeLink) return;
      if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
        adjacency.get(edge.source)?.push(edge.target);
      }
    });

    const visiting = new Set<string>();
    const visited = new Set<string>();

    const dfs = (nodeId: string): boolean => {
      if (visiting.has(nodeId)) return true;
      if (visited.has(nodeId)) return false;
      visiting.add(nodeId);
      for (const next of adjacency.get(nodeId) || []) {
        if (dfs(next)) return true;
      }
      visiting.delete(nodeId);
      visited.add(nodeId);
      return false;
    };

    for (const nodeId of nodeIds) {
      if (dfs(nodeId)) return true;
    }
    return false;
  }, []);

  const resolveRuntimeLoopOverride = useCallback((): {
    enabled: boolean;
    max_node_executions: number;
    max_total_node_executions: number;
  } | null | 'cancelled' => {
    const definition = buildWorkflowDefinition(nodesRef.current, edgesRef.current) as any;
    const loopControl = definition?.loop_control || {};

    if (!hasRuntimeCycle()) {
      return null;
    }

    const shouldRunWithLoop = window.confirm(
      'Loop detected in this workflow. Run with loop mode? Click Cancel to stop execution.',
    );
    if (!shouldRunWithLoop) {
      toast('Execution cancelled. Enable loop mode to run this loop workflow.', { icon: '⚠️' });
      return 'cancelled';
    }

    const defaultValue = String(loopControl.max_node_executions ?? DEFAULT_LOOP_CONTROL.max_node_executions);
    const rawValue = window.prompt(
      'Loop detected. Enter repeat count for this run:',
      defaultValue,
    );
    if (rawValue === null) {
      toast('Execution cancelled by user.', { icon: 'ℹ️' });
      return 'cancelled';
    }

    const parsed = Number.parseInt(rawValue.trim(), 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
      toast.error('Please enter a valid repeat count (integer >= 1).');
      return 'cancelled';
    }

    const configuredMaxTotal = Number(loopControl.max_total_node_executions ?? DEFAULT_LOOP_CONTROL.max_total_node_executions);
    const safeMaxTotal = Number.isFinite(configuredMaxTotal)
      ? Math.max(configuredMaxTotal, parsed)
      : Math.max(DEFAULT_LOOP_CONTROL.max_total_node_executions, parsed);

    return {
      enabled: true,
      max_node_executions: parsed,
      max_total_node_executions: safeMaxTotal,
    };
  }, [buildWorkflowDefinition, hasRuntimeCycle]);

  const startExecutionFromTrigger = useCallback(async (trigger: WorkflowNode) => {
    if (!isPollingEnabled) {
      toast.error(WORKFLOW_INACTIVE_ERROR_MESSAGE);
      return;
    }
    if (ensureWorkflowSaved) {
      const synced = await ensureWorkflowSaved();
      if (!synced) {
        return;
      }
    }
    resetNodeExecutionVisualState();
    const shouldResolveLoopOverride =
      trigger.data.type === 'manual_trigger' || trigger.data.type === 'schedule_trigger';
    const runtimeLoopOverride = shouldResolveLoopOverride ? resolveRuntimeLoopOverride() : null;
    if (runtimeLoopOverride === 'cancelled') {
      return;
    }

    try {
      if (trigger.data.type === 'manual_trigger') {
        const enqueue = await executionService.runWorkflow(workflowId, {
          start_node_id: trigger.id,
          loop_control_override: runtimeLoopOverride || undefined,
        });
        toast.success('Workflow execution started!');
        beginExecutionTracking(enqueue.execution_id, {
          triggeredBy: enqueue.triggered_by,
          primeNodeId: trigger.id,
        });
      } else if (trigger.data.type === 'form_trigger') {
        const formUrl = buildFormPageUrl(workflowId, trigger.id);
        const opened = window.open(formUrl, '_blank');
        if (opened) {
          toast.success('Form opened in a new tab. Submit there to continue execution.');
        } else {
          toast(`Popup blocked. Open this form URL manually: ${formUrl}`, { duration: 7000 });
        }
      } else if (trigger.data.type === 'webhook_trigger') {
        const method = String(trigger.data?.config?.method || 'POST').toUpperCase();
        toast.success(`Webhook trigger: Use HTTP ${method} to the webhook endpoint to trigger this workflow`, { duration: 5000 });
      } else if (trigger.data.type === 'schedule_trigger') {
        const enqueue = await executionService.runWorkflowSchedule(workflowId, {
          start_node_id: trigger.id,
          respect_schedule: false,
          loop_control_override: runtimeLoopOverride || undefined,
        });
        toast.success(
          'Manual schedule test run queued now. Automatic recurring runs need a published workflow with Celery beat + worker running.',
        );
        beginExecutionTracking(enqueue.execution_id, {
          triggeredBy: enqueue.triggered_by,
        });
      } else {
        toast.error(`Unsupported trigger type: ${trigger.data.type}`);
      }
    } catch (error) {
      console.error('Execution failed:', error);
      const message = toUserFriendlyErrorMessage(
        (error as any)?.response?.data?.detail,
        'Workflow execution failed. Check console for details.',
      );
      toast.error(message);
    }
  }, [beginExecutionTracking, ensureWorkflowSaved, isPollingEnabled, resetNodeExecutionVisualState, resolveRuntimeLoopOverride, workflowId]);

  const runSelectedFlowOption = useCallback(async (trigger: WorkflowNode) => {
    setIsStartingSelectedFlow(true);
    try {
      await startExecutionFromTrigger(trigger);
      setShowRunFlowSelector(false);
      setRunFlowOptions([]);
    } finally {
      setIsStartingSelectedFlow(false);
    }
  }, [startExecutionFromTrigger]);

  const handleRunWorkflow = useCallback(async () => {
    if (isCanvasReadOnlyPreviewMode) {
      if (isVersionPreviewMode) {
        toast('Exit version preview before executing workflow.', { icon: 'ℹ️' });
      } else {
        toast('Accept or discard the AI preview before executing workflow.', { icon: 'ℹ️' });
      }
      return;
    }

    if (workflowId === 'new') {
      toast.error('Please save your workflow before running');
      return;
    }
    if (!isPollingEnabled) {
      toast.error(WORKFLOW_INACTIVE_ERROR_MESSAGE);
      return;
    }

    const triggerCandidates = nodes.filter((node) => {
      return TRIGGER_NODE_TYPES.includes(node.data.type as typeof TRIGGER_NODE_TYPES[number]) || node.type === 'trigger';
    }) as WorkflowNode[];
    const rootTriggers = triggerCandidates.filter((node) => !edges.some((edge) => edge.target === node.id));

    if (rootTriggers.length === 0) {
      if (triggerCandidates.length === 0) {
        toast.error('No trigger nodes found in workflow. Please add a Manual Trigger, Form Trigger, Schedule Trigger, Webhook Trigger, or Workflow Trigger node.');
        return;
      }

      if (triggerCandidates.length === 1) {
        toast('Trigger node has incoming connections, but execution will continue using the single available trigger. Make sure trigger nodes have no incoming edges.', { icon: '⚠️' });
        const trigger = triggerCandidates[0];
        await startExecutionFromTrigger(trigger);
        return;
      }

      toast.error('All trigger nodes have incoming connections. Trigger nodes should not have any incoming edges.');
      return;
    }

    if (rootTriggers.length > 1) {
      const selectedTrigger = selectedNodeId
        ? rootTriggers.find((trigger) => trigger.id === selectedNodeId)
        : null;
      if (selectedTrigger) {
        await startExecutionFromTrigger(selectedTrigger);
        return;
      }

      setRunFlowOptions(rootTriggers);
      setShowRunFlowSelector(true);
      toast('Multiple independent flows found. Select the flow you want to run.', { icon: 'ℹ️' });
      return;
    }

    const trigger = rootTriggers[0];
    await startExecutionFromTrigger(trigger);
  }, [isCanvasReadOnlyPreviewMode, isVersionPreviewMode, workflowId, isPollingEnabled, nodes, edges, selectedNodeId, startExecutionFromTrigger]);

  useEffect(() => {
    stopPolling();
    activeExecutionIdRef.current = null;
    setActiveExecutionId(null);
    return () => {
      stopPolling();
      activeExecutionIdRef.current = null;
      setActiveExecutionId(null);
    };
  }, [workflowId, stopPolling]);

  const handleStopWorkflow = useCallback(async () => {
    const executionId = activeExecutionIdRef.current;
    if (!executionId) {
      toast('No running execution to stop.', { icon: 'ℹ️' });
      return;
    }
    if (isStoppingExecution) return;

    setIsStoppingExecution(true);
    try {
      const detail = await executionService.stopExecution(executionId);
      stopPolling();
      activeExecutionIdRef.current = null;
      setActiveExecutionId(null);

      setNodes((nds) =>
        nds.map((node) => {
          const result = detail.node_results.find((r) => r.node_id === node.id);
          if (!result) {
            return node;
          }
          return {
            ...node,
            data: {
              ...node.data,
              status: result.status,
              last_execution_result: result,
              last_output: result.output_data ?? node.data.last_output,
            },
          };
        }),
      );

      setExecutionHistory((history) =>
        history.map((entry) =>
          entry.executionId === executionId
            ? {
                ...entry,
                status: detail.status,
                errorMessage: detail.error_message
                  ? toUserFriendlyErrorMessage(detail.error_message, '')
                  : null,
                startedAt: detail.started_at,
                finishedAt: detail.finished_at,
                durationMs:
                  detail.started_at && detail.finished_at
                    ? Date.parse(detail.finished_at) - Date.parse(detail.started_at)
                    : entry.durationMs,
              }
            : entry,
        ),
      );

      executionDetailCacheRef.current[executionId] = detail;
      if (selectedExecutionId === executionId) {
        setSelectedExecutionDetail(detail);
      }
      onExecutionUpdate?.(detail);
      toast.success('Workflow stopped manually.');
    } catch (error: any) {
      const message = toUserFriendlyErrorMessage(
        error?.response?.data?.detail,
        'Failed to stop workflow.',
      );
      toast.error(message);
    } finally {
      setIsStoppingExecution(false);
    }
  }, [isStoppingExecution, onExecutionUpdate, selectedExecutionId, setNodes, stopPolling]);

  const isValidConnection = useCallback((connection: Connection) => {
    if (isReadOnly) {
      return false;
    }
    if (!connection.source || !connection.target) {
      return false;
    }

    // Prevent self-loop connections.
    if (connection.source === connection.target) {
      return false;
    }

    // Allow multiple edges from the same source handle (fan-out),
    // but prevent exact duplicate connections.
    const sourceHandle = connection.sourceHandle ?? null;
    const targetHandle = connection.targetHandle ?? null;
    const duplicateEdge = edges.some(
      (edge) =>
        edge.source === connection.source &&
        edge.target === connection.target &&
        (edge.sourceHandle ?? null) === sourceHandle &&
        (edge.targetHandle ?? null) === targetHandle
    );
    return !duplicateEdge;
  }, [edges, isReadOnly]);

  const onConnect = useCallback((params: Connection) => {
    if (isCanvasReadOnlyPreviewMode) return;
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    if (isAiPreviewMode) return;
    if (!params.source || !params.target) return;
    const existingEdgeIds = new Set(edgesRef.current.map((edge) => edge.id));

    const newEdge: WorkflowEdge = {
      ...params,
      source: params.source,
      target: params.target,
      sourceHandle: params.sourceHandle,
      targetHandle: params.targetHandle,
      branch: params.sourceHandle ?? undefined,
      id: generateUniqueEdgeId(existingEdgeIds),
      type: 'deletable',
      animated: false,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' }
    };
    setEdges((eds) => addEdge(newEdge as any, eds));
    emitCanvasMutation('connect_nodes');
    connectingNode.current = null; // Clear connection state after successful connection
    edgeQuickAddTarget.current = null;
    toast.success('Nodes connected');
  }, [isCanvasReadOnlyPreviewMode, setEdges, emitCanvasMutation, isAiPreviewMode, isReadOnly, notifyReadOnlyEdit]);

  const onConnectStart = useCallback((_: any, {
    nodeId,
    handleId,
    handleType,
  }: {
    nodeId: string | null;
    handleId?: string | null;
    handleType?: 'source' | 'target' | null;
  }) => {
  if (isReadOnly || isCanvasReadOnlyPreviewMode || isAiPreviewMode) {
    connectingNode.current = null;
    edgeQuickAddTarget.current = null;
    return;
  }
    if (!nodeId) {
      connectingNode.current = null;
      edgeQuickAddTarget.current = null;
      return;
    }
    connectingNode.current = {
      nodeId,
      handleId: handleId ?? null,
      connectionType: handleType === 'target' ? 'target' : 'source',
    };
    edgeQuickAddTarget.current = null;
  }, [isReadOnly, isCanvasReadOnlyPreviewMode, isAiPreviewMode]);

  const onConnectEnd = useCallback(
    (event: any) => {
      if (isReadOnly || isCanvasReadOnlyPreviewMode || isAiPreviewMode) return;

      if (!connectingNode.current || !reactFlowInstance) return;

      const targetIsPane = event.target.classList.contains('react-flow__pane');

      if (targetIsPane) {
        const { clientX, clientY } = event instanceof TouchEvent ? event.touches[0] : event;

        const position = reactFlowInstance.screenToFlowPosition({
          x: clientX,
          y: clientY,
        });

        setMenuPosition(position);
        setMenuVisible(true);
      }
    },
    [isReadOnly, isCanvasReadOnlyPreviewMode, isAiPreviewMode, reactFlowInstance]
  );

  const onPaneClick = useCallback(() => {
    setMenuVisible(false);
    setContextMenuState(null);
    connectingNode.current = null; // Clear connection state when clicking on pane
    edgeQuickAddTarget.current = null;
  }, []);

  const updateLastPointerFlowPosition = useCallback((clientX: number, clientY: number) => {
    if (!reactFlowInstance) return;
    lastPointerFlowPositionRef.current = reactFlowInstance.screenToFlowPosition({
      x: clientX,
      y: clientY,
    });
  }, [reactFlowInstance]);

  const openContextMenuAtClientPoint = useCallback((clientX: number, clientY: number, nodeId: string | null) => {
    if (!reactFlowInstance || !reactFlowWrapper.current) return;
    const wrapperRect = reactFlowWrapper.current.getBoundingClientRect();
    const localX = clientX - wrapperRect.left;
    const localY = clientY - wrapperRect.top;
    const menuWidth = 200;
    const menuHeight = 150;
    const alignRight = localX > wrapperRect.width - menuWidth;
    const alignBottom = localY > wrapperRect.height - menuHeight;

    const flowPosition = reactFlowInstance.screenToFlowPosition({ x: clientX, y: clientY });
    lastPointerFlowPositionRef.current = flowPosition;

    setContextMenuState({
      x: localX,
      y: localY,
      flowPosition,
      nodeId,
      alignRight,
      alignBottom,
    });
    setMenuVisible(false);
    connectingNode.current = null;
    edgeQuickAddTarget.current = null;
  }, [reactFlowInstance]);

  const onPaneContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    openContextMenuAtClientPoint(event.clientX, event.clientY, null);
  }, [openContextMenuAtClientPoint]);

  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: WorkflowNode) => {
    event.preventDefault();
    openContextMenuAtClientPoint(event.clientX, event.clientY, node.id);
  }, [openContextMenuAtClientPoint]);

  const onPaneMouseMove = useCallback((event: React.MouseEvent) => {
    updateLastPointerFlowPosition(event.clientX, event.clientY);
  }, [updateLastPointerFlowPosition]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = isReadOnly ? 'none' : 'move';
  }, [isReadOnly]);

  const onDrop = useCallback(
  (event: React.DragEvent) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }

    if (isCanvasReadOnlyPreviewMode || isAiPreviewMode) {
      toast('Accept or discard the AI preview before editing.', {
        icon: 'ℹ️',
      });
      return;
    }

    event.preventDefault();

      if (!reactFlowWrapper.current || !reactFlowInstance) return;

      const nodeType = event.dataTransfer.getData('application/reactflow');
      if (!nodeType) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      addNodeAtPosition(nodeType, position);
    },
    [
      isCanvasReadOnlyPreviewMode,
      isAiPreviewMode,
      isReadOnly,
      notifyReadOnlyEdit,
      reactFlowInstance,
    ]
    );

    const addNodeAtPosition = useCallback((type: string, position: XYPosition) => {
      if (isReadOnly) {
        notifyReadOnlyEdit();
        return;
      }

    if (isCanvasReadOnlyPreviewMode || isAiPreviewMode) {
      toast('Accept or discard the AI preview before editing.', {
        icon: 'ℹ️',
      });
        return;
      }
    if (
      type === 'workflow_trigger'
      && nodesRef.current.some((node) => node.data.type === 'workflow_trigger')
    ) {
      toast.error('Only one Workflow Trigger allowed per workflow');
      return;
    }
    try {
      const newNode = createNode(type, position);
      newNode.data.is_active = isNodeActive(newNode.data.is_active);
      newNode.data.onToggleActive = toggleNodeActive;
      const newNodeId = newNode.id;

      setNodes((nds) => nds.concat(newNode));
      emitCanvasMutation('add_node');
      toast.success(`${newNode.data.label} added`);

      if (edgeQuickAddTarget.current || connectingNode.current) {
        const existingEdgeIds = new Set(edgesRef.current.map((edge) => edge.id));
        const buildEdge = (
          edgeSource: string,
          edgeTarget: string,
          edgeSourceHandle: string | null,
          edgeTargetHandle: string | null,
          edgeBranch?: string,
        ): WorkflowEdge => ({
          id: generateUniqueEdgeId(existingEdgeIds),
          source: edgeSource,
          target: edgeTarget,
          sourceHandle: edgeSourceHandle,
          targetHandle: edgeTargetHandle,
          branch: edgeBranch,
          type: 'deletable',
          animated: true,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#94a3b8',
          },
        });

        if (edgeQuickAddTarget.current) {
          const edgeContext = edgeQuickAddTarget.current;
          const edgeToSplit = edgesRef.current.find((edge) => edge.id === edgeContext.edgeId);

          if (edgeToSplit) {
            const upstreamSourceHandle = edgeToSplit.sourceHandle ?? edgeContext.sourceHandle ?? null;
            const downstreamTargetHandle = edgeToSplit.targetHandle ?? edgeContext.targetHandle ?? null;
            const upstreamBranch =
              readEdgeBranch(edgeToSplit)
              ?? (upstreamSourceHandle === null ? undefined : String(upstreamSourceHandle));

            const sourceToNew = buildEdge(
              edgeToSplit.source,
              newNodeId,
              upstreamSourceHandle,
              null,
              upstreamBranch,
            );
            const newToTarget = buildEdge(
              newNodeId,
              edgeToSplit.target,
              null,
              downstreamTargetHandle,
              undefined,
            );

            setEdges((eds) => [
              ...eds.filter((edge) => edge.id !== edgeToSplit.id),
              sourceToNew,
              newToTarget,
            ]);
            emitCanvasMutation('quick_add_insert_between_edge');
          }
        } else if (connectingNode.current) {
          const { nodeId: anchorNodeId, handleId, connectionType } = connectingNode.current;
          const sourceHandle = handleId ?? undefined;
          const newEdge: WorkflowEdge =
            connectionType === 'target'
              ? buildEdge(
                  newNodeId,
                  anchorNodeId,
                  null,
                  handleId ?? null,
                  undefined,
                )
              : buildEdge(
                  anchorNodeId,
                  newNodeId,
                  handleId ?? null,
                  null,
                  sourceHandle ?? undefined,
                );
          setEdges((eds) => addEdge(newEdge, eds));
          emitCanvasMutation('quick_add_connect');
        }

        connectingNode.current = null;
        edgeQuickAddTarget.current = null;
      }

      setMenuVisible(false);
    } catch (error) {
      console.error(error);
    }
  }, [
    emitCanvasMutation,
    isCanvasReadOnlyPreviewMode,
    isAiPreviewMode,
    isReadOnly,
    notifyReadOnlyEdit,
    setEdges,
    setNodes,
    toggleNodeActive,
    previewEditBlockMessage
  ]);

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: any) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }

    if (isCanvasReadOnlyPreviewMode || isAiPreviewMode) return;

    setSelectedNodeId(node.id);
  }, [
    isCanvasReadOnlyPreviewMode,
    isAiPreviewMode,
    isReadOnly,
    notifyReadOnlyEdit,
  ]);

  const openQuickAddAtCenter = useCallback(() => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    if (!reactFlowInstance || !reactFlowWrapper.current) return;
    const rect = reactFlowWrapper.current.getBoundingClientRect();
    const centerPosition = reactFlowInstance.screenToFlowPosition({
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
    connectingNode.current = null;
    edgeQuickAddTarget.current = null;
    setMenuPosition(centerPosition);
    setMenuVisible(true);
  }, [isReadOnly, notifyReadOnlyEdit, reactFlowInstance]);

  const handleAddFirstStepFromStarter = useCallback(() => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    setHasPickedNewWorkflowStarter(true);
    if (typeof (window as any).openNodePalette === 'function') {
      (window as any).openNodePalette();
      return;
    }
    openQuickAddAtCenter();
  }, [isReadOnly, notifyReadOnlyEdit, openQuickAddAtCenter]);

  const handleBuildWithAiFromStarter = useCallback(() => {
    setHasPickedNewWorkflowStarter(true);
    if (!isAiAssistantOpen) {
      onToggleAiAssistant?.();
    }
    toast('Describe your workflow to build the first draft with AI.', { icon: '✨' });
  }, [isAiAssistantOpen, onToggleAiAssistant]);

  // Serialization logic for the backend
  const getWorkflowData = useCallback((name: string) => {
    return {
      name,
      definition: buildWorkflowDefinition(nodes, edges),
    };
  }, [nodes, edges, buildWorkflowDefinition]);

  // Deserialization logic (restore from backend format)
  const loadWorkflowData = useCallback((definition: any, options?: { resetHistory?: boolean }) => {
    if (!definition) return;
    workflowLoopControlRef.current = {
      ...DEFAULT_LOOP_CONTROL,
      ...(definition.loop_control || {}),
    };
    const incomingNodeCount = Array.isArray(definition.nodes) ? definition.nodes.length : 0;
    const incomingEdgeCount = Array.isArray(definition.edges) ? definition.edges.length : 0;
    if (workflowId === 'new' && incomingNodeCount === 0 && incomingEdgeCount === 0) {
      setHasPickedNewWorkflowStarter(false);
    }

    const switchBranchLookup = buildSwitchBranchLookup(definition.nodes || []);
    const nodeTypeById = new Map<string, string>(
      (definition.nodes || []).map((node: any) => [String(node.id), String(node.type || '')]),
    );

    // Map simplified nodes back to React Flow format
    const rfNodes: WorkflowNode[] = (definition.nodes || []).map((n: any) => {
      const category = NODE_LIBRARY.trigger.some(ref => ref.type === n.type) ? 'trigger' :
        NODE_LIBRARY.action.some(ref => ref.type === n.type) ? 'action' :
          NODE_LIBRARY.transform.some(ref => ref.type === n.type) ? 'transform' :
            NODE_LIBRARY.input_output.some(ref => ref.type === n.type) ? 'input_output' : 'ai';
      const normalizedConfig = stripConfigEditorMetadata(
        n.type === 'switch'
          ? normalizeSwitchNodeConfig(n.config)
          : n.type === 'if_else'
            ? normalizeIfElseNodeConfig(n.config)
            : n.type === 'merge'
              ? normalizeMergeConfigForEditor(n.config)
              : n.config,
      );

      return {
        id: n.id,
        type: category,
        position: n.position,
        data: {
          label: n.label,
          config: normalizedConfig,
          type: n.type,
          category: category,
          is_active: isNodeActive(n.is_active),
          onToggleActive: toggleNodeActive,
          schedule_is_active: isScheduleVisualActive(
            n.type,
            normalizedConfig,
            isPublished,
          ),
        }
      };
    });

    isHydratingCanvasRef.current = true;
    setNodes(rfNodes);

    // Map simplified edges back to React Flow format with handle awareness
    const rfEdges = (definition.edges || []).map((e: any) => {
      const sourceNodeType = nodeTypeById.get(String(e.source));
      const rawBranch = e.branch ?? e.sourceHandle ?? null;
      let normalizedBranch: string | null = rawBranch ? String(rawBranch) : null;

      if (sourceNodeType === 'switch') {
        normalizedBranch = normalizeSwitchEdgeBranch(
          normalizedBranch,
          switchBranchLookup.get(String(e.source)),
        );
      } else if (sourceNodeType === 'if_else') {
        const branch = String(normalizedBranch || '').trim();
        normalizedBranch = branch === 'true' || branch === 'false' ? branch : normalizedBranch;
      }

      const sourceHandle = e.sourceHandle ?? normalizedBranch ?? null;
      return {
        ...e,
        type: 'deletable',
        sourceHandle,
        targetHandle: e.targetHandle || null,
        branch: normalizedBranch ?? undefined,
        animated: false,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      };
    });

    setEdges(rfEdges);
    if (options?.resetHistory !== false) {
      resetUndoRedoHistory({
        nodes: (definition.nodes || []).map((node: any) => ({
          id: node.id,
          type: node.type,
          label: node.label,
          position: node.position,
          config: node.config || {},
          is_active: isNodeActive(node.is_active),
        })),
        edges: rfEdges.map((edge: any) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle || null,
          targetHandle: edge.targetHandle || null,
          branch: edge.branch ?? undefined,
        })),
        loop_control: {
          ...DEFAULT_LOOP_CONTROL,
          ...(definition.loop_control || {}),
        },
      });
    }

    requestAnimationFrame(() => {
      isHydratingCanvasRef.current = false;
    });
  }, [setNodes, setEdges, resetUndoRedoHistory, workflowId, isPublished, toggleNodeActive]);

  const applyHistoryEntry = useCallback((entry: CanvasHistoryEntry) => {
    isApplyingHistoryRef.current = true;
    loadWorkflowData(entry.definition, { resetHistory: false });
    requestAnimationFrame(() => {
      isApplyingHistoryRef.current = false;
    });
  }, [loadWorkflowData]);

  const undoCanvas = useCallback(() => {
    flushPendingHistoryCommit();
    if (historyIndexRef.current <= 0) {
      return;
    }

    historyIndexRef.current -= 1;
    const entry = historyStackRef.current[historyIndexRef.current];
    updateUndoRedoAvailability();
    if (entry) {
      applyHistoryEntry(entry);
      onCanvasMutated?.('undo');
    }
  }, [applyHistoryEntry, flushPendingHistoryCommit, onCanvasMutated, updateUndoRedoAvailability]);

  const redoCanvas = useCallback(() => {
    flushPendingHistoryCommit();
    if (historyIndexRef.current >= historyStackRef.current.length - 1) {
      return;
    }

    historyIndexRef.current += 1;
    const entry = historyStackRef.current[historyIndexRef.current];
    updateUndoRedoAvailability();
    if (entry) {
      applyHistoryEntry(entry);
      onCanvasMutated?.('redo');
    }
  }, [applyHistoryEntry, flushPendingHistoryCommit, onCanvasMutated, updateUndoRedoAvailability]);

  const markDefinitionAsClean = useCallback((definition: any) => {
    if (!definition) return;
    setInitialData(JSON.stringify({
      nodes: (definition.nodes || []).map((node: any) => ({ ...node, position: node.position })),
      edges: definition.edges || [],
    }));
  }, []);

  const loadWorkflowVersions = useCallback(async (options?: { silent?: boolean }) => {
    if (!workflowId || workflowId === 'new') {
      setIsVersionsLoading(false);
      setWorkflowVersions([]);
      setCurrentVersionId(null);
      setSelectedVersionId(null);
      setSelectedVersionDetail(null);
      setVersionsError(null);
      return;
    }

    if (!options?.silent) {
      setIsVersionsLoading(true);
    }
    setVersionsError(null);
    try {
      const versions = await workflowService.listWorkflowVersions(workflowId);
      setWorkflowVersions(versions);
      setCurrentVersionId((previous) => {
        if (previous && versions.some((version) => version.id === previous)) {
          return previous;
        }
        return versions[0]?.id || null;
      });
      if (versions.length === 0) {
        setSelectedVersionId(null);
        setSelectedVersionDetail(null);
      }
    } catch (error: any) {
      console.error('Failed to load workflow versions:', error);
      const message = toUserFriendlyErrorMessage(
        error?.response?.data?.detail,
        'Failed to load versions.',
      );
      setVersionsError(message);
    } finally {
      if (!options?.silent) {
        setIsVersionsLoading(false);
      }
    }
  }, [workflowId]);

  const exitVersionPreview = useCallback((options?: { silent?: boolean }) => {
    const baseDefinition = versionPreviewBaseDefinitionRef.current;
    setVersionPreviewMeta(null);
    versionPreviewBaseDefinitionRef.current = null;
    setSelectedNodeId(null);
    if (baseDefinition) {
      loadWorkflowData(baseDefinition, { resetHistory: false });
      window.setTimeout(() => {
        reactFlowInstance?.fitView({ duration: 450, padding: 0.2 });
      }, 20);
    }
    if (!options?.silent) {
      toast('Exited version preview.', { icon: 'ℹ️' });
    }
  }, [loadWorkflowData, reactFlowInstance]);

  const previewWorkflowVersion = useCallback(async (versionId: string) => {
    if (!workflowId || workflowId === 'new') {
      toast.error('Save workflow first to preview versions.');
      return;
    }
    if (isAiPreviewMode) {
      toast('Accept or discard the AI preview first.', { icon: 'ℹ️' });
      return;
    }

    setSelectedVersionId(versionId);
    setVersionsError(null);
    setIsVersionDetailLoading(true);
    try {
      const detail = await workflowService.getWorkflowVersion(workflowId, versionId) as WorkflowVersionDetail;
      if (!detail?.snapshot_json?.definition) {
        toast.error('Selected version has no previewable snapshot.');
        return;
      }

      if (!versionPreviewBaseDefinitionRef.current) {
        versionPreviewBaseDefinitionRef.current = buildWorkflowDefinition(nodesRef.current, edgesRef.current);
      }
      setSelectedVersionDetail(detail);
      setVersionPreviewMeta({
        versionId: detail.id,
        versionNumber: detail.version_number,
      });
      setSelectedNodeId(null);
      loadWorkflowData(detail.snapshot_json.definition, { resetHistory: false });
      setActiveTab('editor');
      window.setTimeout(() => {
        reactFlowInstance?.fitView({ duration: 550, padding: 0.22 });
      }, 20);
      toast(`Previewing version v${detail.version_number}.`, { icon: 'ℹ️' });
    } catch (error: any) {
      console.error('Failed to preview workflow version:', error);
      const message = toUserFriendlyErrorMessage(
        error?.response?.data?.detail,
        'Failed to preview selected version.',
      );
      setVersionsError(message);
      toast.error(message);
    } finally {
      setIsVersionDetailLoading(false);
    }
  }, [buildWorkflowDefinition, isAiPreviewMode, loadWorkflowData, reactFlowInstance, workflowId]);

  const restoreWorkflowVersion = useCallback(async (versionId: string) => {
    if (!workflowId || workflowId === 'new') {
      toast.error('Save workflow first to restore versions.');
      return;
    }
    if (isPublished) {
      toast.error(PUBLISHED_WORKFLOW_EDIT_MESSAGE);
      return;
    }
    const targetVersion = workflowVersions.find((version) => version.id === versionId) || null;
    const versionLabel = targetVersion ? `v${targetVersion.version_number}` : 'this version';
    const confirmed = window.confirm(
      `Restore ${versionLabel} as current workflow? Your current draft on canvas will be replaced.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      const restoredWorkflow = await toast.promise(
        workflowService.restoreWorkflowVersion(workflowId, versionId),
        {
          loading: `Restoring ${versionLabel}...`,
          success: <b>Workflow restored successfully.</b>,
          error: <b>Could not restore selected version.</b>,
        }
      );
      setCurrentVersionId(versionId);
      setSelectedVersionId(versionId);
      setVersionPreviewMeta(null);
      versionPreviewBaseDefinitionRef.current = null;
      setSelectedVersionDetail(null);
      setSelectedNodeId(null);

      loadWorkflowData(restoredWorkflow.definition);
      markDefinitionAsClean(restoredWorkflow.definition);
      window.dispatchEvent(new CustomEvent('autoflow:workflow-restored', {
        detail: restoredWorkflow,
      }));
      await loadWorkflowVersions({ silent: true });
      setActiveTab('editor');
      window.setTimeout(() => {
        reactFlowInstance?.fitView({ duration: 550, padding: 0.22 });
      }, 20);
    } catch (error) {
      console.error('Failed to restore workflow version:', error);
    }
  }, [isPublished, loadWorkflowData, loadWorkflowVersions, markDefinitionAsClean, reactFlowInstance, workflowId, workflowVersions]);

  useEffect(() => {
    setIsVersionsLoading(false);
    setVersionPreviewMeta(null);
    versionPreviewBaseDefinitionRef.current = null;
    setSelectedVersionId(null);
    setSelectedVersionDetail(null);
    setVersionsError(null);
    setWorkflowVersions([]);
    setCurrentVersionId(null);

    if (workflowId && workflowId !== 'new') {
      void loadWorkflowVersions();
    }
  }, [workflowId, loadWorkflowVersions]);

  useEffect(() => {
    if (activeTab !== 'versions') return;
    if (!workflowId || workflowId === 'new') return;
    void loadWorkflowVersions({ silent: false });
  }, [activeTab, loadWorkflowVersions, workflowId]);

  const getSelectedCanvasNodes = useCallback((preferredNodeId?: string | null): WorkflowNode[] => {
    const currentNodes = nodesRef.current;
    if (preferredNodeId) {
      const preferredNode = currentNodes.find((node) => node.id === preferredNodeId) || null;
      if (!preferredNode) return [];
      const selected = currentNodes.filter((node) => Boolean(node.selected));
      if (selected.length > 0 && selected.some((node) => node.id === preferredNodeId)) {
        return selected;
      }
      return [preferredNode];
    }

    const selected = currentNodes.filter((node) => Boolean(node.selected));
    if (selected.length > 0) return selected;
    if (!selectedNodeId) return [];
    const focusedNode = currentNodes.find((node) => node.id === selectedNodeId);
    return focusedNode ? [focusedNode] : [];
  }, [selectedNodeId]);

  const copySelectedNodesToClipboard = useCallback((preferredNodeId?: string | null): boolean => {
    if (activeTab !== 'editor') return false;
    if (isCanvasReadOnlyPreviewMode) {
      toast(previewEditBlockMessage, { icon: 'ℹ️' });
      return false;
    }

    const selectedNodes = getSelectedCanvasNodes(preferredNodeId);
    if (selectedNodes.length === 0) {
      toast('Select at least one node to copy.', { icon: 'ℹ️' });
      return false;
    }

    const selectedIds = new Set(selectedNodes.map((node) => node.id));
    const copiedNodes: WorkflowClipboardNode[] = selectedNodes.map((node) => {
      const { onToggleActive: _ignoredToggle, ...dataWithoutHandlers } = node.data;
      return {
        id: node.id,
        type: node.type,
        position: { ...node.position },
        data: {
          ...dataWithoutHandlers,
          config: cloneNodeConfig(node.data.config),
        },
      };
    });

    const copiedEdges: WorkflowClipboardEdge[] = edgesRef.current
      .filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target))
      .map((edge: WorkflowEdge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? null,
        targetHandle: edge.targetHandle ?? null,
        branch: readEdgeBranch(edge),
        type: edge.type,
        animated: edge.animated,
        style: edge.style ? { ...edge.style } : undefined,
        markerEnd: edge.markerEnd ?? undefined,
      }));

    const nextPayload: WorkflowClipboardPayload = {
      version: WORKFLOW_CLIPBOARD_VERSION,
      sourceWorkflowId: workflowId,
      copiedAtMs: Date.now(),
      nodes: copiedNodes,
      edges: copiedEdges,
    };
    workflowClipboardRef.current = nextPayload;
    persistWorkflowClipboard(nextPayload);
    setHasClipboardData(true);
    clipboardPasteCountRef.current = 0;

    toast.success(`Copied ${copiedNodes.length} nodes, ${copiedEdges.length} edges.`);
    return true;
  }, [activeTab, getSelectedCanvasNodes, isCanvasReadOnlyPreviewMode, previewEditBlockMessage, workflowId]);

  const pasteWorkflowClipboard = useCallback((options?: { anchorPosition?: XYPosition | null }): boolean => {
    if (activeTab !== 'editor') return false;
    if (isCanvasReadOnlyPreviewMode) {
      toast(previewEditBlockMessage, { icon: 'ℹ️' });
      return false;
    }

    const payload = workflowClipboardRef.current || readWorkflowClipboardFromStorage();
    if (payload) {
      workflowClipboardRef.current = payload;
      setHasClipboardData(true);
    }
    if (!payload || payload.version !== WORKFLOW_CLIPBOARD_VERSION || payload.nodes.length === 0) {
      setHasClipboardData(false);
      toast('Copy some nodes first.', { icon: 'ℹ️' });
      return false;
    }

    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;
    const existingNodeIds = new Set(currentNodes.map((node) => node.id));
    const existingEdgeIds = new Set(currentEdges.map((edge) => edge.id));

    const hasWorkflowTrigger = currentNodes.some((node) => node.data.type === 'workflow_trigger');
    let canPasteWorkflowTrigger = !hasWorkflowTrigger;
    const nodesToPaste = payload.nodes.filter((node) => {
      if (node.data.type !== 'workflow_trigger') return true;
      if (!canPasteWorkflowTrigger) return false;
      canPasteWorkflowTrigger = false;
      return true;
    });
    const skippedWorkflowTriggerCount = payload.nodes.length - nodesToPaste.length;

    if (nodesToPaste.length === 0) {
      toast.error('Cannot paste: Workflow Trigger already exists in this workflow.');
      return false;
    }

    clipboardPasteCountRef.current += 1;
    const pasteOffsetX = DUPLICATE_NODE_OFFSET_X * clipboardPasteCountRef.current;
    const pasteOffsetY = DUPLICATE_NODE_OFFSET_Y * clipboardPasteCountRef.current;
    const isCrossWorkflowPaste = payload.sourceWorkflowId !== workflowId;
    const preferredAnchor = options?.anchorPosition
      || lastPointerFlowPositionRef.current
      || null;

    const sourceMinX = Math.min(...nodesToPaste.map((node) => Number(node.position.x || 0)));
    const sourceMinY = Math.min(...nodesToPaste.map((node) => Number(node.position.y || 0)));
    const sourceMaxX = Math.max(...nodesToPaste.map((node) => Number(node.position.x || 0)));
    const sourceMaxY = Math.max(...nodesToPaste.map((node) => Number(node.position.y || 0)));
    const sourceWidth = Math.max(0, sourceMaxX - sourceMinX);
    const sourceHeight = Math.max(0, sourceMaxY - sourceMinY);
    let pasteAnchor: XYPosition | null = null;
    if (preferredAnchor) {
      pasteAnchor = preferredAnchor;
    } else if (isCrossWorkflowPaste && reactFlowInstance) {
      const rect = reactFlowWrapper.current?.getBoundingClientRect();
      const screenCenter = rect
        ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
        : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
      const flowCenter = reactFlowInstance.screenToFlowPosition(screenCenter);
      pasteAnchor = {
        x: flowCenter.x - sourceWidth / 2,
        y: flowCenter.y - sourceHeight / 2,
      };
    }

    const nodeIdMap = new Map<string, string>();
    const pastedNodes: WorkflowNode[] = nodesToPaste.map((node, index) => {
      const newId = generateUniqueNodeId(existingNodeIds, node.data.type || String(node.type || 'node'));
      nodeIdMap.set(node.id, newId);
      const copiedConfig = cloneNodeConfig(node.data.config);
      const position = pasteAnchor
        ? {
            x: pasteAnchor.x + (node.position.x - sourceMinX) + pasteOffsetX,
            y: pasteAnchor.y + (node.position.y - sourceMinY) + pasteOffsetY,
          }
        : {
            x: node.position.x + pasteOffsetX,
            y: node.position.y + pasteOffsetY,
          };
      return {
        ...node,
        id: newId,
        position,
        selected: index === 0,
        data: {
          ...node.data,
          label: buildCopiedLabel(String(node.data.label || ''), String(node.data.type || 'node')),
          config: copiedConfig,
          is_active: isNodeActive(node.data.is_active),
          onToggleActive: toggleNodeActive,
          status: 'PENDING',
          last_execution_result: null,
          last_output: undefined,
          schedule_is_active: isScheduleVisualActive(
            node.data.type,
            copiedConfig,
            isPublished,
          ),
        },
      };
    });

    const pastedEdges: WorkflowEdge[] = payload.edges
      .filter((edge) => nodeIdMap.has(edge.source) && nodeIdMap.has(edge.target))
      .map((edge) => {
        const mappedSource = nodeIdMap.get(edge.source) as string;
        const mappedTarget = nodeIdMap.get(edge.target) as string;
        return {
          ...edge,
          id: generateUniqueEdgeId(existingEdgeIds),
          source: mappedSource,
          target: mappedTarget,
          sourceHandle: edge.sourceHandle ?? null,
          targetHandle: edge.targetHandle ?? null,
          branch: edge.branch ?? undefined,
          type: edge.type || 'deletable',
          animated: false,
          style: edge.style ? { ...edge.style } : { stroke: '#94a3b8', strokeWidth: 2 },
          markerEnd: edge.markerEnd ? { ...edge.markerEnd } : { type: MarkerType.ArrowClosed, color: '#94a3b8' },
        };
      });

    setNodes((nds) => {
      const deselectedExisting: WorkflowNode[] = nds.map((node) => ({ ...node, selected: false }));
      return deselectedExisting.concat(pastedNodes);
    });
    if (pastedEdges.length > 0) {
      setEdges((eds) => eds.concat(pastedEdges));
    }
    setSelectedNodeId(null);
    triggerClipboardMutationFeedback(
      pastedNodes.map((node) => node.id),
      pastedEdges.map((edge) => edge.id),
    );
    emitCanvasMutation('paste_nodes');

    if (skippedWorkflowTriggerCount > 0) {
      const skippedTriggerLabel = skippedWorkflowTriggerCount === 1 ? 'Workflow Trigger' : 'Workflow Triggers';
      toast(`Pasted ${pastedNodes.length} nodes, ${pastedEdges.length} edges. Skipped ${skippedWorkflowTriggerCount} ${skippedTriggerLabel}.`, {
        icon: '⚠️',
      });
      return true;
    }
    toast.success(`Pasted ${pastedNodes.length} nodes, ${pastedEdges.length} edges.`);
    return true;
  }, [activeTab, emitCanvasMutation, isCanvasReadOnlyPreviewMode, isPublished, previewEditBlockMessage, reactFlowInstance, setEdges, setNodes, toggleNodeActive, triggerClipboardMutationFeedback, workflowId]);

  const duplicateSelectedNodes = useCallback((preferredNodeId?: string | null) => {
    if (activeTab !== 'editor') return;
    if (isCanvasReadOnlyPreviewMode) {
      toast(previewEditBlockMessage, { icon: 'ℹ️' });
      return;
    }

    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;
    const selectedNodes = getSelectedCanvasNodes(preferredNodeId);

    if (selectedNodes.length === 0) {
      toast('Select at least one node to duplicate.', { icon: 'ℹ️' });
      return;
    }

    const selectedIds = new Set(selectedNodes.map((node) => node.id));
    const duplicateableNodes = selectedNodes.filter((node) => node.data.type !== 'workflow_trigger');
    const skippedWorkflowTriggerCount = selectedNodes.length - duplicateableNodes.length;

    if (duplicateableNodes.length === 0) {
      toast.error('Workflow Trigger node cannot be duplicated.');
      return;
    }

    const existingNodeIds = new Set(currentNodes.map((node) => node.id));

    const nodeIdMap = new Map<string, string>();
    const duplicatedNodes: WorkflowNode[] = duplicateableNodes.map((node, index) => {
      const newId = generateUniqueNodeId(existingNodeIds, String(node.data.type || node.type || 'node'));
      nodeIdMap.set(node.id, newId);
      const copiedConfig = cloneNodeConfig(node.data.config);
      const normalizedIsActive = isNodeActive(node.data.is_active);

      return {
        ...node,
        id: newId,
        position: {
          x: node.position.x + DUPLICATE_NODE_OFFSET_X,
          y: node.position.y + DUPLICATE_NODE_OFFSET_Y,
        },
        selected: index === 0,
        data: {
          ...node.data,
          label: buildCopiedLabel(String(node.data.label || ''), String(node.data.type || 'node')),
          config: copiedConfig,
          is_active: normalizedIsActive,
          onToggleActive: toggleNodeActive,
          status: 'PENDING',
          last_execution_result: null,
          last_output: undefined,
          schedule_is_active: isScheduleVisualActive(
            node.data.type,
            copiedConfig,
            isPublished,
          ),
          workflow_execution_visual_active: node.data.workflow_execution_visual_active,
        },
      };
    });

    const existingEdgeIds = new Set(currentEdges.map((edge) => edge.id));

    const duplicatedEdges: WorkflowEdge[] = currentEdges
      .filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target))
      .filter((edge) => nodeIdMap.has(edge.source) && nodeIdMap.has(edge.target))
      .map((edge) => {
        const mappedSource = nodeIdMap.get(edge.source) as string;
        const mappedTarget = nodeIdMap.get(edge.target) as string;

        return {
          ...edge,
          id: generateUniqueEdgeId(existingEdgeIds),
          source: mappedSource,
          target: mappedTarget,
          animated: false,
        };
      });

    setNodes((nds) => {
      const deselectedExisting: WorkflowNode[] = nds.map((node) => ({ ...node, selected: false }));
      return deselectedExisting.concat(duplicatedNodes);
    });
    if (duplicatedEdges.length > 0) {
      setEdges((eds) => eds.concat(duplicatedEdges));
    }
    setSelectedNodeId(null);
    triggerClipboardMutationFeedback(
      duplicatedNodes.map((node) => node.id),
      duplicatedEdges.map((edge) => edge.id),
    );
    emitCanvasMutation('duplicate_nodes');

    if (skippedWorkflowTriggerCount > 0) {
      const skippedMessage = skippedWorkflowTriggerCount === 1 ? '1 Workflow Trigger' : `${skippedWorkflowTriggerCount} Workflow Triggers`;
      toast(`Duplicated ${duplicatedNodes.length} nodes, ${duplicatedEdges.length} edges. Skipped ${skippedMessage}.`, {
        icon: '⚠️',
      });
      return;
    }
    toast.success(`Duplicated ${duplicatedNodes.length} nodes, ${duplicatedEdges.length} edges.`);
  }, [
    activeTab,
    emitCanvasMutation,
    getSelectedCanvasNodes,
    isCanvasReadOnlyPreviewMode,
    isPublished,
    previewEditBlockMessage,
    setEdges,
    setNodes,
    toggleNodeActive,
    triggerClipboardMutationFeedback,
  ]);

  useEffect(() => {
    const isTextInputTarget = (target: EventTarget | null) => {
      const element = target as HTMLElement | null;
      if (!element) return false;
      const tagName = element.tagName?.toLowerCase();
      return (
        element.isContentEditable ||
        tagName === 'input' ||
        tagName === 'textarea' ||
        tagName === 'select'
      );
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isTextInputTarget(event.target)) {
        return;
      }

      const isModifierPressed = event.metaKey || event.ctrlKey;
      if (!isModifierPressed || event.altKey) {
        return;
      }

      const key = event.key.toLowerCase();
      const isUndo = key === 'z' && !event.shiftKey;
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y';
      const isDuplicate = key === 'd' && !event.shiftKey;
      const isCopy = key === 'c' && !event.shiftKey;
      const isPaste = key === 'v' && !event.shiftKey;
      const isEditShortcut = isUndo || isRedo || isDuplicate || isCopy || isPaste;

      if (isVersionPreviewMode && isEditShortcut) {
        event.preventDefault();
        toast('Exit version preview before editing.', { icon: 'ℹ️' });
        return;
      }

      if (isUndo) {
        event.preventDefault();
        undoCanvas();
      } else if (isRedo) {
        event.preventDefault();
        redoCanvas();
      } else if (isDuplicate) {
        event.preventDefault();
        duplicateSelectedNodes();
      } else if (isCopy) {
        if (copySelectedNodesToClipboard()) {
          event.preventDefault();
        }
      } else if (isPaste) {
        if (pasteWorkflowClipboard()) {
          event.preventDefault();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoCanvas, redoCanvas, duplicateSelectedNodes, copySelectedNodesToClipboard, pasteWorkflowClipboard, isVersionPreviewMode]);

  useEffect(() => {
    return () => {
      clearPendingHistoryCommit();
      clearAiApplyTimers();
      clearClipboardHighlightTimer();
    };
  }, [clearPendingHistoryCommit, clearAiApplyTimers, clearClipboardHighlightTimer]);

  // Unsaved changes tracking
  const [initialData, setInitialData] = useState<string>('');
  
  useEffect(() => {
    // When a workflow is loaded, capture its initial state
    if (nodes.length > 0 || edges.length > 0) {
      if (!initialData) {
        setInitialData(JSON.stringify({ nodes, edges }));
      }
    }
  }, [workflowId, nodes.length, edges.length]);

  const isDirty = useMemo(() => {
    if (!initialData && (nodes.length > 0 || edges.length > 0)) return true;
    if (!initialData) return false;
    return initialData !== JSON.stringify({ nodes, edges });
  }, [nodes, edges, initialData]);

  // Expose serialization helpers
  useEffect(() => {
    (window as any).getCanvasWorkflowData = getWorkflowData;
    (window as any).loadCanvasWorkflowData = (definition: any) => {
      loadWorkflowData(definition);
      // Reset dirty state on load
      setInitialData(JSON.stringify({ 
        nodes: definition.nodes.map((n: any) => ({ ...n, position: n.position })), 
        edges: definition.edges 
      }));
    };
    (window as any).applyAiWorkflow = (definition: any) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return false;
    }

    if (isVersionPreviewMode) {
      toast('Exit version preview before applying AI workflow.', {
        icon: 'ℹ️',
      });
      return false;
    }
      const graph = buildAiGraphFromDefinition(definition);
      applyAiGraphToCanvas(graph);
      return true;
    };
    (window as any).previewAiWorkflow = (definition: any, options?: { name?: string }) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return false;
    }

    if (isVersionPreviewMode) {
      toast('Exit version preview before starting AI preview.', {
        icon: 'ℹ️',
      });
      return false;
    }
      const graph = buildAiGraphFromDefinition(definition);
      setSelectedNodeId(null);
      setAiPreviewGraph({
        ...graph,
        name: options?.name || graph.name || '',
      });
      window.setTimeout(() => {
        reactFlowInstance?.fitView({ duration: 550, padding: 0.22 });
      }, 20);
      return true;
    };
    (window as any).acceptAiWorkflowPreview = () => {
      if (isReadOnly) {
        notifyReadOnlyEdit();
        return false;
      }
      if (!aiPreviewGraph) return false;
      applyAiGraphToCanvas(aiPreviewGraph);
      return true;
    };
    (window as any).discardAiWorkflowPreview = () => {
      if (!aiPreviewGraph) return false;
      setAiPreviewGraph(null);
      setSelectedNodeId(null);
      window.setTimeout(() => {
        reactFlowInstance?.fitView({ duration: 450, padding: 0.2 });
      }, 20);
      return true;
    };
    (window as any).isAiWorkflowPreviewActive = () => Boolean(aiPreviewGraph);
    (window as any).getAiWorkflowPreviewName = () => aiPreviewGraph?.name || '';
    (window as any).clearAiWorkflowPreview = () => {
      setAiPreviewGraph(null);
      setSelectedNodeId(null);
    };
    (window as any).isVersionWorkflowPreviewActive = () => Boolean(versionPreviewMeta);
    (window as any).exitVersionWorkflowPreview = () => {
      if (!versionPreviewMeta) return false;
      exitVersionPreview({ silent: true });
      return true;
    };
    (window as any).isCanvasDirty = () => isDirty;
    (window as any).undoCanvas = undoCanvas;
    (window as any).redoCanvas = redoCanvas;

    (window as any).addNodeAtCenter = (type: string) => {
      if (isReadOnly) {
        notifyReadOnlyEdit();
        return;
      }

      if (isCanvasReadOnlyPreviewMode || aiPreviewGraph) {
        toast('Accept or discard the AI preview before editing.', {
          icon: 'ℹ️',
        });
        return;
      }
      if (!reactFlowInstance) return;
      
      let position: XYPosition;
      
      if (connectingNode.current) {
        const sourceNode = nodes.find(n => n.id === connectingNode.current?.nodeId);
        position = {
          x: connectingNode.current.connectionType === 'target'
            ? (sourceNode?.position.x || 0)
            : (sourceNode?.position.x || 0) + 250,
          y: connectingNode.current.connectionType === 'target'
            ? (sourceNode?.position.y || 0) + 160
            : (sourceNode?.position.y || 0),
        };
      } else {
        reactFlowInstance.getViewport();
        position = reactFlowInstance.screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        });
      }
      
      addNodeAtPosition(type, position);
    };

    return () => {
      delete (window as any).getCanvasWorkflowData;
      delete (window as any).loadCanvasWorkflowData;
      delete (window as any).applyAiWorkflow;
      delete (window as any).previewAiWorkflow;
      delete (window as any).acceptAiWorkflowPreview;
      delete (window as any).discardAiWorkflowPreview;
      delete (window as any).isAiWorkflowPreviewActive;
      delete (window as any).getAiWorkflowPreviewName;
      delete (window as any).clearAiWorkflowPreview;
      delete (window as any).isVersionWorkflowPreviewActive;
      delete (window as any).exitVersionWorkflowPreview;
      delete (window as any).isCanvasDirty;
      delete (window as any).undoCanvas;
      delete (window as any).redoCanvas;
    };
  }, [
    getWorkflowData,
    loadWorkflowData,
    isDirty,
    reactFlowInstance,
    undoCanvas,
    redoCanvas,
    aiPreviewGraph,
    isCanvasReadOnlyPreviewMode,
    isVersionPreviewMode,
    exitVersionPreview,
    versionPreviewMeta,
    previewEditBlockMessage,
    addNodeAtPosition,
    applyAiGraphToCanvas,
    buildAiGraphFromDefinition,
    isReadOnly,
    notifyReadOnlyEdit,
  ]);

  const updateNodeConfig = useCallback((id: string, config: Record<string, any>, output?: any) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          const normalizedConfig = stripConfigEditorMetadata(
            node.data.type === 'if_else'
              ? normalizeIfElseNodeConfig(config)
              : config,
          );
          const scheduleIsActive = isScheduleVisualActive(
            node.data.type,
            normalizedConfig,
            isPublished,
          );
          return {
            ...node,
            data: {
              ...node.data,
              config: normalizedConfig,
              // Preserve latest execution view while config gets normalized
              // (for example, sheet mapping defaults). Execution state will be
              // refreshed by execution polling/history APIs.
              status: node.data.status,
              last_execution_result: node.data.last_execution_result,
              last_output: output === undefined ? node.data.last_output : output,
              schedule_is_active: scheduleIsActive,
            },
          };
        }
        return node;
      })
    );
    emitCanvasMutation('node_config_change');
  }, [emitCanvasMutation, isPublished, isReadOnly, notifyReadOnlyEdit, setNodes]);

  const updateNodeLabel = useCallback((id: string, label: string) => {
    if (isReadOnly) {
      notifyReadOnlyEdit();
      return;
    }
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== id) return node;
        return {
          ...node,
          data: {
            ...node.data,
            label,
          },
        };
      })
    );
    emitCanvasMutation('node_label_change');
  }, [emitCanvasMutation, isReadOnly, notifyReadOnlyEdit, setNodes]);

  const getUpstreamData = (nodeId: string) => {
    const upstreamEdges = edges
      .filter(e => e.target === nodeId)
      .filter((edge) => {
        // Ignore AI config sub-node links. These are not regular upstream
        // payload edges and should not pollute input preview.
        const handle = String(edge.targetHandle || '');
        const targetNode = nodes.find((n) => n.id === edge.target);
        const targetType = targetNode?.data?.type || '';
        const sourceNode = nodes.find((n) => n.id === edge.source);
        const sourceType = sourceNode?.data?.type || '';
        const isAiAgentTarget = targetType === 'ai_agent';
        const isAiChildHandle = AI_AGENT_CHILD_HANDLES.includes(handle as (typeof AI_AGENT_CHILD_HANDLES)[number]);
        const isChatModelSource =
          sourceType === 'chat_model_openai' || sourceType === 'chat_model_groq';
        if (isAiAgentTarget && (isAiChildHandle || isChatModelSource)) {
          return false;
        }
        return true;
      }) as WorkflowEdge[];
    if (upstreamEdges.length === 0) return null;

    const combinedData: Record<string, any> = {};
    let hasRealUpstreamOutput = false;

    const isPlainObject = (value: any): value is Record<string, any> => (
      value !== null && typeof value === 'object' && !Array.isArray(value)
    );

    upstreamEdges.forEach(edge => {
      const sourceNode = nodes.find(n => n.id === edge.source);
      const lastOutput = sourceNode?.data.last_output;
      const executionOutput = sourceNode?.data.last_execution_result?.output_data;
      const resolvedOutput = lastOutput ?? executionOutput;

      if (resolvedOutput !== null && typeof resolvedOutput !== 'undefined') {
        hasRealUpstreamOutput = true;

        if (isPlainObject(resolvedOutput)) {
          Object.assign(combinedData, resolvedOutput);
        } else if (Array.isArray(resolvedOutput)) {
          // Preserve array outputs for step-by-step node testing.
          combinedData[`${edge.source}_output`] = resolvedOutput;
          combinedData._default = resolvedOutput;
        } else {
          // Preserve scalar outputs for step-by-step node testing.
          combinedData[`${edge.source}_output`] = resolvedOutput;
          combinedData._default = resolvedOutput;
        }
      }
    });

    if (!hasRealUpstreamOutput || Object.keys(combinedData).length === 0) {
      return null;
    }

    return combinedData;
  };

  const getNodeById = useCallback((nodeId: string) => {
    return nodes.find((node) => node.id === nodeId) || null;
  }, [nodes]);

  const sortNavigationNodes = useCallback((items: WorkflowNode[]) => {
    return [...items].sort((a, b) => {
      if (a.position.x !== b.position.x) return a.position.x - b.position.x;
      if (a.position.y !== b.position.y) return a.position.y - b.position.y;
      return a.data.label.localeCompare(b.data.label);
    });
  }, []);

  const selectedNode =
    isCanvasReadOnlyPreviewMode || isAiPreviewMode || isReadOnly
      ? null
      : nodes.find(n => n.id === selectedNodeId);

  const upstreamData =
    isCanvasReadOnlyPreviewMode || isAiPreviewMode || isReadOnly
      ? null
      : (selectedNodeId ? getUpstreamData(selectedNodeId) : null);

  const contextMenuTargetNodes = useMemo(
    () => getSelectedCanvasNodes(contextMenuState?.nodeId),
    [contextMenuState?.nodeId, getSelectedCanvasNodes],
  );

  const canContextCopyOrDuplicate =
    activeTab === 'editor' &&
    !isCanvasReadOnlyPreviewMode &&
    !isAiPreviewMode &&
    !isReadOnly &&
    contextMenuTargetNodes.length > 0;

  const canContextPaste =
    activeTab === 'editor' &&
    !isCanvasReadOnlyPreviewMode &&
    !isAiPreviewMode &&
    !isReadOnly &&
    hasClipboardData;

  const contextCopyDisabledReason =
    isReadOnly
      ? 'Workflow is published and read-only'
      : isCanvasReadOnlyPreviewMode
        ? (isVersionPreviewMode
            ? 'Disabled in version preview mode'
            : 'Disabled in AI preview mode')
        : contextMenuTargetNodes.length < 1
          ? 'No nodes available to copy'
          : '';

  const contextPasteDisabledReason =
    isReadOnly
      ? 'Workflow is published and read-only'
      : isCanvasReadOnlyPreviewMode
        ? (isVersionPreviewMode
            ? 'Disabled in version preview mode'
            : 'Disabled in AI preview mode')
        : !hasClipboardData
          ? 'Clipboard is empty'
          : '';
  const previousNodes = useMemo(() => {
    if (isCanvasReadOnlyPreviewMode) return [] as WorkflowNode[];
    if (!selectedNodeId) return [] as WorkflowNode[];
    const uniqueIds = Array.from(new Set(
      edges
        .filter((edge) => edge.target === selectedNodeId)
        .map((edge) => edge.source),
    ));
    const connectedNodes = uniqueIds
      .map((nodeId) => getNodeById(nodeId))
      .filter((node): node is WorkflowNode => Boolean(node));
    return sortNavigationNodes(connectedNodes);
  }, [isCanvasReadOnlyPreviewMode, selectedNodeId, edges, getNodeById, sortNavigationNodes]);

  const nextNodes = useMemo(() => {
    if (isCanvasReadOnlyPreviewMode) return [] as WorkflowNode[];
    if (!selectedNodeId) return [] as WorkflowNode[];
    const uniqueIds = Array.from(new Set(
      edges
        .filter((edge) => edge.source === selectedNodeId)
        .map((edge) => edge.target),
    ));
    const connectedNodes = uniqueIds
      .map((nodeId) => getNodeById(nodeId))
      .filter((node): node is WorkflowNode => Boolean(node));
    return sortNavigationNodes(connectedNodes);
  }, [isCanvasReadOnlyPreviewMode, selectedNodeId, edges, getNodeById, sortNavigationNodes]);

  const graphNodes = aiPreviewGraph?.nodes || nodes;
  const graphEdges = aiPreviewGraph?.edges || edges;
  const recentAiNodeIdSet = useMemo(() => new Set(recentAiNodeIds), [recentAiNodeIds]);
  const recentAiEdgeIdSet = useMemo(() => new Set(recentAiEdgeIds), [recentAiEdgeIds]);
  const recentClipboardNodeIdSet = useMemo(() => new Set(recentClipboardNodeIds), [recentClipboardNodeIds]);
  const recentClipboardEdgeIdSet = useMemo(() => new Set(recentClipboardEdgeIds), [recentClipboardEdgeIds]);
  const highlightedNodeIdSet = useMemo(
    () => new Set([...recentAiNodeIdSet, ...recentClipboardNodeIdSet]),
    [recentAiNodeIdSet, recentClipboardNodeIdSet],
  );
  const highlightedEdgeIdSet = useMemo(
    () => new Set([...recentAiEdgeIdSet, ...recentClipboardEdgeIdSet]),
    [recentAiEdgeIdSet, recentClipboardEdgeIdSet],
  );

  const displayNodes = useMemo(() => {
    if (highlightedNodeIdSet.size === 0) {
      return graphNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          is_read_only: isReadOnly,
        },
      }));
    }

    return graphNodes.map((node) => {
      const withReadOnly = {
        ...node,
        data: {
          ...node.data,
          is_read_only: isReadOnly,
        },
      };

      if (
        recentAiNodeIdSet.size === 0 ||
        !recentAiNodeIdSet.has(node.id) ||
        !highlightedNodeIdSet.has(node.id)
      ) {
        return withReadOnly;
      }
      const existingClass = node.className ? `${node.className} ` : '';
      return {
        ...withReadOnly,
        className: `${existingClass}ai-node-updated`,
      };
    });
  }, [graphNodes, highlightedNodeIdSet, isReadOnly, recentAiNodeIdSet]);

  const displayEdges = useMemo(() => {
    if (highlightedEdgeIdSet.size === 0) {
      return graphEdges.map((edge) => ({
        ...edge,
        data: {
          ...(edge.data || {}),
          isReadOnly,
        },
      }));
    }

    return graphEdges.map((edge) => {
      const withReadOnly = {
        ...edge,
        data: {
          ...(edge.data || {}),
          isReadOnly,
        },
      };

      if (
        recentAiEdgeIdSet.size === 0 ||
        !recentAiEdgeIdSet.has(edge.id) ||
        !highlightedEdgeIdSet.has(edge.id)
      ) {
        return withReadOnly;
      }
      return {
        ...withReadOnly,
        animated: true,
        style: {
          ...(edge.style || {}),
          stroke: '#3b82f6',
          strokeWidth: 2.6,
          strokeDasharray: '8 6',
        },
      };
    });
  }, [graphEdges, highlightedEdgeIdSet, isReadOnly, recentAiEdgeIdSet]);

  const showNewWorkflowStarter =
    activeTab === 'editor' &&
    workflowId === 'new' &&
    nodes.length === 0 &&
    !isCanvasReadOnlyPreviewMode &&
    !hasPickedNewWorkflowStarter &&
    !isAiApplyingChanges;

  return (
    <div className="flex-1 flex flex-col relative h-full bg-slate-50 dark:bg-slate-950 overflow-hidden">
      <div className="absolute left-1/2 top-5 z-20 -translate-x-1/2">
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2 shadow-lg">
          <button
            onClick={onToggleAiAssistant}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition ${isAiAssistantOpen
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
          >
            <Sparkles size={16} className={`${isAiAssistantOpen ? 'animate-pulse' : ''}`} />
            <span className="hidden sm:inline">{isAiAssistantOpen ? 'Close AI' : 'AI'}</span>
          </button>
          <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 mx-1" />
          <button
            onClick={() => setActiveTab('editor')}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${activeTab === 'editor'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
          >
            Editor
          </button>
          <button
            onClick={() => setActiveTab('executions')}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${activeTab === 'executions'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
          >
            Executions
          </button>
          <button
            onClick={() => setActiveTab('versions')}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${activeTab === 'versions'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
          >
            Versions
          </button>
          <div className="text-xs text-slate-500 dark:text-slate-400 ml-3">
            {activeTab === 'versions'
              ? (workflowVersions.length > 0
                ? `${workflowVersions.length} version${workflowVersions.length > 1 ? 's' : ''} recorded`
                : 'No versions yet')
              : (executionHistory.length > 0
                ? `${executionHistory.length} execution${executionHistory.length > 1 ? 's' : ''} recorded`
                : 'No executions yet')
            }
          </div>
          <div className="w-px h-6 bg-slate-200 dark:bg-slate-700 mx-1" />
          <button
            type="button"
            onClick={() => {
              if (isReadOnly) {
                notifyReadOnlyEdit();
                return;
              }
              onTogglePollingEnabled?.();
            }}
            className={`group flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition ${
              isReadOnly ? 'cursor-not-allowed opacity-70' : 'hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
            title={isReadOnly ? 'Unpublish to change active state' : isPollingEnabled ? 'Set workflow inactive' : 'Set workflow active'}
          >
            <span className={`text-[11px] font-semibold ${isPollingEnabled ? 'text-emerald-700 dark:text-emerald-300' : 'text-slate-500 dark:text-slate-400'}`}>
              {isPollingEnabled ? 'Active' : 'Inactive'}
            </span>
            <span
              className={`relative inline-flex h-5 w-10 items-center rounded-full transition ${
                isPollingEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
                  isPollingEnabled ? 'translate-x-5' : 'translate-x-1'
                }`}
              />
            </span>
          </button>
        </div>
      </div>
      {activeTab === 'editor' ? (
        <ReactFlowProvider>
          <div className="flex-1 relative pt-16" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onInit={setReactFlowInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onPaneMouseMove={onPaneMouseMove}
            onPaneContextMenu={onPaneContextMenu}
            onNodeContextMenu={onNodeContextMenu}
            onNodeDoubleClick={onNodeDoubleClick}
            onPaneClick={onPaneClick}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            deleteKeyCode={
              isReadOnly || isCanvasReadOnlyPreviewMode || isAiPreviewMode
                ? null
                : ['Delete', 'Backspace']
            }
            nodesDraggable={
              !isCanvasReadOnlyPreviewMode &&
              !isAiPreviewMode &&
              !isReadOnly
            }
            nodesConnectable={
              !isCanvasReadOnlyPreviewMode &&
              !isAiPreviewMode &&
              !isReadOnly
            }
            edgesUpdatable={
              !isCanvasReadOnlyPreviewMode &&
              !isAiPreviewMode &&
              !isReadOnly
            }
            elementsSelectable={!isCanvasReadOnlyPreviewMode && !isAiPreviewMode}
            nodesFocusable={!isCanvasReadOnlyPreviewMode && !isAiPreviewMode}
            edgesFocusable={!isCanvasReadOnlyPreviewMode && !isAiPreviewMode}
            fitView
            >
            {showNewWorkflowStarter && (
              <div className="pointer-events-none absolute inset-0 z-[915] flex items-center justify-center">
                <div className="-mt-12 flex items-center gap-8 sm:gap-12 pointer-events-auto">
                  <button
                    type="button"
                    onClick={handleAddFirstStepFromStarter}
                    className="group flex flex-col items-center gap-3"
                  >
                    <div className="h-28 w-28 rounded-2xl border-2 border-dashed border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/45 flex items-center justify-center transition-all duration-200 group-hover:border-blue-500/70 group-hover:dark:border-blue-400/70 group-hover:bg-white dark:group-hover:bg-slate-900">
                      <Plus size={36} className="text-slate-500 dark:text-slate-300 group-hover:text-blue-600 dark:group-hover:text-blue-300" />
                    </div>
                    <span className="text-xl font-medium text-slate-700 dark:text-slate-200 tracking-tight">
                      Add first step...
                    </span>
                  </button>

                  <span className="text-base text-slate-400 dark:text-slate-500 font-medium">or</span>

                  <button
                    type="button"
                    onClick={handleBuildWithAiFromStarter}
                    className="group flex flex-col items-center gap-3"
                  >
                    <div className="h-28 w-28 rounded-2xl border-2 border-dashed border-slate-300 dark:border-slate-600 bg-white/75 dark:bg-slate-900/45 flex items-center justify-center transition-all duration-200 group-hover:border-indigo-500/70 group-hover:dark:border-indigo-400/70 group-hover:bg-white dark:group-hover:bg-slate-900">
                      <Sparkles size={34} className="text-slate-500 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-300" />
                    </div>
                    <span className="text-xl font-medium text-slate-700 dark:text-slate-200 tracking-tight">
                      Build with AI
                    </span>
                  </button>
                </div>
              </div>
            )}

            {isAiPreviewMode && (
              <div className="pointer-events-none absolute left-1/2 top-20 z-[920] -translate-x-1/2 rounded-2xl border border-amber-300/90 bg-amber-50/95 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.11em] text-amber-700 shadow-[0_14px_38px_rgba(217,119,6,0.2)] dark:border-amber-700/70 dark:bg-amber-900/35 dark:text-amber-200">
                Preview Mode{aiPreviewGraph?.name ? ` · ${aiPreviewGraph.name}` : ''} · accept or discard from AI panel
              </div>
            )}

            {isVersionPreviewMode && (
              <div className="absolute left-1/2 top-20 z-[920] -translate-x-1/2 rounded-2xl border border-cyan-300/90 bg-cyan-50/95 px-4 py-2 shadow-[0_14px_38px_rgba(8,145,178,0.22)] dark:border-cyan-700/70 dark:bg-cyan-900/35">
                <div className="flex items-center gap-3 text-[11px] font-bold uppercase tracking-[0.11em] text-cyan-700 dark:text-cyan-200">
                  <span>
                    Version Preview · v{versionPreviewMeta?.versionNumber}
                  </span>
                  <button
                    type="button"
                    onClick={() => exitVersionPreview()}
                    className="rounded-lg border border-cyan-300/80 bg-white/80 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-cyan-700 hover:bg-white dark:border-cyan-600/70 dark:bg-cyan-950/40 dark:text-cyan-100 dark:hover:bg-cyan-950/70"
                  >
                    Exit Preview
                  </button>
                  {versionPreviewMeta?.versionId && versionPreviewMeta.versionId !== currentVersionId && (
                    <button
                      type="button"
                      onClick={() => void restoreWorkflowVersion(versionPreviewMeta.versionId)}
                      className="rounded-lg border border-cyan-500/80 bg-cyan-600 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-white hover:bg-cyan-700 dark:border-cyan-500/70 dark:bg-cyan-500 dark:hover:bg-cyan-400"
                    >
                      Restore Workflow
                    </button>
                  )}
                </div>
              </div>
            )}

            {isAiApplyingChanges && (
              <div className="pointer-events-none absolute inset-0 z-[950]">
                <div className="absolute inset-0 bg-blue-500/5 dark:bg-blue-400/10 backdrop-blur-[1px]" />
                <div className="absolute left-1/2 top-20 -translate-x-1/2 rounded-2xl border border-blue-200/80 dark:border-blue-500/30 bg-white/95 dark:bg-slate-900/90 px-4 py-3 shadow-[0_20px_50px_rgba(37,99,235,0.2)]">
                  <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-blue-700 dark:text-blue-300">
                    <Loader2 size={14} className="animate-spin" />
                    Applying AI changes on canvas
                  </div>
                  <div className="mt-2 h-1.5 w-56 overflow-hidden rounded-full bg-blue-100 dark:bg-blue-500/20">
                    <div className="h-full w-16 rounded-full bg-blue-600 dark:bg-blue-400 ai-canvas-progress" />
                  </div>
                </div>
              </div>
            )}

            {/* Floating Action Buttons - Bottom Center */}
            <div
              className="absolute left-1/2 -translate-x-1/2 z-[1000] flex flex-row items-center gap-4 animate-in fade-in slide-in-from-bottom-6 duration-500"
              style={{ bottom: footerOffset + 24 }}
            >
              <button
                onClick={undoCanvas}
                disabled={!canUndo}
                title="Undo (Ctrl/Cmd+Z)"
                className="group flex items-center justify-center bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 w-10 h-10 rounded-xl border border-slate-200 dark:border-slate-700 shadow-[0_20px_40px_rgba(0,0,0,0.1)] transition-all duration-300 disabled:opacity-45 disabled:cursor-not-allowed enabled:hover:bg-slate-900 enabled:dark:hover:bg-slate-700 enabled:hover:text-white"
              >
                <Undo2 size={16} className="transition-transform duration-300 group-enabled:group-hover:-translate-x-0.5" />
              </button>

              <button
                onClick={redoCanvas}
                disabled={!canRedo}
                title="Redo (Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y)"
                className="group flex items-center justify-center bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 w-10 h-10 rounded-xl border border-slate-200 dark:border-slate-700 shadow-[0_20px_40px_rgba(0,0,0,0.1)] transition-all duration-300 disabled:opacity-45 disabled:cursor-not-allowed enabled:hover:bg-slate-900 enabled:dark:hover:bg-slate-700 enabled:hover:text-white"
              >
                <Redo2 size={16} className="transition-transform duration-300 group-enabled:group-hover:translate-x-0.5" />
              </button>

              {!isAligned && (
                <button
                  onClick={alignNodes}
                  className="group flex items-center gap-2 bg-white dark:bg-slate-800 hover:bg-slate-900 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 hover:text-white dark:hover:text-white px-5 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-[0_20px_40px_rgba(0,0,0,0.1)] transition-all duration-300"
                >
                  <LayoutGrid size={18} className="group-hover:rotate-90 transition-transform duration-500" />
                  <span className="text-xs font-black uppercase tracking-[0.1em]">Perfect Align</span>
                </button>
              )}

              <button
                onClick={handleRunWorkflow}
                disabled={!isPollingEnabled}
                title={isPollingEnabled ? 'Execute Workflow' : 'Activate workflow to execute'}
                className="group flex items-center gap-3 bg-blue-600 hover:bg-blue-700 text-white px-7 py-3 rounded-2xl border border-blue-500 shadow-[0_20px_40px_rgba(37,99,235,0.3)] transition-all duration-300 active:scale-95 disabled:opacity-45 disabled:cursor-not-allowed"
              >
                <div className="relative">
                  <Play size={18} fill="currentColor" stroke="none" className="group-hover:scale-110 transition-transform" />
                  <div className="absolute inset-0 bg-white/20 rounded-full scale-150 opacity-0 group-hover:animate-ping" />
                </div>
                <span className="text-xs font-black uppercase tracking-[0.1em]">Execute Workflow</span>
              </button>

              <button
                onClick={handleStopWorkflow}
                disabled={!activeExecutionId || isStoppingExecution}
                title={activeExecutionId ? 'Stop Running Workflow' : 'No running workflow'}
                className="group flex items-center justify-center bg-rose-600 hover:bg-rose-700 text-white w-12 h-12 rounded-2xl border border-rose-500 shadow-[0_20px_40px_rgba(244,63,94,0.28)] transition-all duration-300 active:scale-95 disabled:opacity-45 disabled:cursor-not-allowed"
              >
                {isStoppingExecution ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Square size={14} fill="currentColor" stroke="none" className="group-enabled:group-hover:scale-105 transition-transform" />
                )}
              </button>
            </div>

            {contextMenuState && (
              <div
                className="absolute z-[1200] min-w-[190px] rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-[0_18px_50px_rgba(15,23,42,0.25)] p-2"
                style={{
                  left: contextMenuState.x,
                  top: contextMenuState.y,
                  transform: `translate(${contextMenuState.alignRight ? '-100%' : '0%'}, ${contextMenuState.alignBottom ? '-100%' : '0%'})`,
                }}
                onMouseDown={(event) => event.stopPropagation()}
                onContextMenu={(event) => event.preventDefault()}
              >
                <button
                  type="button"
                  disabled={!canContextCopyOrDuplicate}
                  title={canContextCopyOrDuplicate ? 'Copy (Ctrl/Cmd+C)' : contextCopyDisabledReason}
                  onClick={() => {
                    if (!canContextCopyOrDuplicate) return;
                    copySelectedNodesToClipboard(contextMenuState.nodeId);
                    setContextMenuState(null);
                  }}
                  className="w-full text-left rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-45 disabled:cursor-not-allowed"
                >
                  Copy
                </button>
                <button
                  type="button"
                  disabled={!canContextPaste}
                  title={canContextPaste ? 'Paste here (Ctrl/Cmd+V)' : contextPasteDisabledReason}
                  onClick={() => {
                    if (!canContextPaste) return;
                    pasteWorkflowClipboard({ anchorPosition: contextMenuState.flowPosition });
                    setContextMenuState(null);
                  }}
                  className="w-full text-left rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-45 disabled:cursor-not-allowed"
                >
                  Paste Here
                </button>
                <button
                  type="button"
                  disabled={!canContextCopyOrDuplicate}
                  title={canContextCopyOrDuplicate ? 'Duplicate (Ctrl/Cmd+D)' : contextCopyDisabledReason}
                  onClick={() => {
                    if (!canContextCopyOrDuplicate) return;
                    duplicateSelectedNodes(contextMenuState.nodeId);
                    setContextMenuState(null);
                  }}
                  className="w-full text-left rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-45 disabled:cursor-not-allowed"
                >
                  Duplicate
                </button>
              </div>
            )}

            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1}
              color={isDark ? '#ffffff' : '#000000'}
            />
            <Controls
              position="bottom-right"
              className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg !mr-[230px]"
              style={{ bottom: footerOffset + 16 }}
            />
            <MiniMap
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg !m-4 overflow-hidden"
              style={{ bottom: footerOffset + 16 }}
              nodeColor={(n) => {
                const data = n.data as WorkflowNodeData;
                if (data.category === 'trigger') return '#10b981';
                if (data.category === 'action') return '#3b82f6';
                if (data.category === 'transform') return '#f59e0b';
                if (data.category === 'input_output') return '#06b6d4';
                if (data.category === 'utility') return '#a855f7';
                if (data.category === 'ai') return '#a855f7';
                return isDark ? '#334155' : '#cbd5e1';
              }}
              maskColor={isDark ? 'rgba(15, 23, 42, 0.7)' : 'rgba(241, 245, 249, 0.7)'}
              pannable
              zoomable
            />

            {menuVisible && menuPosition && (
              <div
                className="absolute z-[1000] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] p-4 w-72 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200 pointer-events-auto"
                style={{
                  left: (reactFlowInstance && menuPosition) ? reactFlowInstance.flowToScreenPosition(menuPosition).x - (reactFlowWrapper.current?.getBoundingClientRect().left || 0) : 0,
                  top: (reactFlowInstance && menuPosition) ? reactFlowInstance.flowToScreenPosition(menuPosition).y - (reactFlowWrapper.current?.getBoundingClientRect().top || 0) : 0,
                  transform: 'translate(-50%, -50%)'
                }}
              >
                <div className="flex items-center justify-between border-b border-slate-50 dark:border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                    <h3 className="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Quick Add Node</h3>
                  </div>
                  <button
                    onClick={() => setMenuVisible(false)}
                    className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md transition-colors text-slate-400 dark:text-slate-600 hover:text-slate-600 dark:hover:text-slate-400"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                  </button>
                </div>

                {/* Quick Add Search */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    ref={menuSearchRef}
                    type="text"
                    placeholder="Search nodes..."
                    value={menuSearchTerm}
                    onChange={(e) => setMenuSearchTerm(e.target.value)}
                    className="w-full pl-9 pr-4 py-1.5 bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-slate-700 dark:text-slate-200"
                  />
                </div>

                <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1 custom-scrollbar">
                  {Object.entries(NODE_LIBRARY).map(([category, nodes]) => {
                    const filteredNodes = nodes.filter(node => 
                      node.label.toLowerCase().includes(menuSearchTerm.toLowerCase()) || 
                      node.description.toLowerCase().includes(menuSearchTerm.toLowerCase())
                    );
                    
                    if (filteredNodes.length === 0) return null;

                    return (
                      <div key={category} className="mb-2 last:mb-0">
                        <div className="text-[10px] font-bold uppercase text-slate-300 dark:text-slate-600 mb-2 ml-1 tracking-widest">
                          {category.replace(/_/g, ' ')}
                        </div>
                        <div className="grid grid-cols-1 gap-1">
                          {filteredNodes.map(node => (
                            <button
                              key={node.type}
                              onClick={() => {
                                if (menuPosition) {
                                  addNodeAtPosition(node.type, menuPosition);
                                  setMenuVisible(false);
                                }
                              }}
                              className="flex flex-col gap-0.5 p-2.5 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 border border-transparent hover:border-slate-100 dark:hover:border-slate-700 transition-all text-left group"
                            >
                              <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ring-4 ring-white dark:ring-slate-900 shadow-sm ${category === 'trigger' ? 'bg-emerald-400' :
                                  category === 'action' ? 'bg-blue-400' :
                                    category === 'transform' ? 'bg-amber-400' :
                                      category === 'input_output' ? 'bg-cyan-400' : 'bg-purple-400'
                                  }`} />
                                <span className="text-sm font-bold text-slate-700 dark:text-slate-200 group-hover:text-blue-600 dark:group-hover:text-blue-400">{node.label}</span>
                              </div>
                              <span className="text-[10px] text-slate-400 dark:text-slate-500 ml-4 line-clamp-1">{node.description}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                  
                  {menuSearchTerm && Object.values(NODE_LIBRARY).every(nodes => 
                    nodes.filter(node => 
                      node.label.toLowerCase().includes(menuSearchTerm.toLowerCase()) || 
                      node.description.toLowerCase().includes(menuSearchTerm.toLowerCase())
                    ).length === 0
                  ) && (
                    <div className="flex flex-col items-center justify-center py-4 text-center">
                      <p className="text-[10px] font-medium text-slate-400">No nodes matching "{menuSearchTerm}"</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {showRunFlowSelector && (
              <div
                className="fixed inset-0 z-[9998] bg-slate-900/55 backdrop-blur-sm flex items-center justify-center p-4"
                onMouseDown={() => {
                  if (isStartingSelectedFlow) return;
                  setShowRunFlowSelector(false);
                  setRunFlowOptions([]);
                }}
              >
                <div
                  className="w-full max-w-xl rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-[0_30px_80px_rgba(0,0,0,0.35)] p-6"
                  onMouseDown={(event) => event.stopPropagation()}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-base font-black text-slate-900 dark:text-slate-100">Select Flow To Run</h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                        Multiple trigger flows were found on this canvas. Choose one trigger to run only that flow.
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={isStartingSelectedFlow}
                      onClick={() => {
                        setShowRunFlowSelector(false);
                        setRunFlowOptions([]);
                      }}
                      className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                    </button>
                  </div>

                  <div className="mt-5 space-y-2 max-h-72 overflow-y-auto pr-1">
                    {runFlowOptions.map((trigger) => (
                      <button
                        key={trigger.id}
                        type="button"
                        disabled={isStartingSelectedFlow}
                        onClick={() => void runSelectedFlowOption(trigger)}
                        className="w-full text-left rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 hover:border-blue-300 hover:bg-blue-50/50 dark:hover:bg-blue-500/10 transition-colors px-4 py-3 disabled:opacity-60"
                      >
                        <div className="text-sm font-bold text-slate-800 dark:text-slate-100">
                          {trigger.data.label || trigger.id}
                        </div>
                        <div className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 mt-1">
                          {trigger.data.type} • node id: {trigger.id}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Trigger Form Modal */}
            {showTriggerForm && triggerNode && (
              <div className="fixed inset-0 z-[9999] bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 md:p-8 animate-in fade-in zoom-in-95 duration-300">
                <div className="bg-white w-full max-w-2xl rounded-[2.5rem] shadow-[0_40px_100px_rgba(0,0,0,0.5)] overflow-hidden border border-white/20">
                  <div className="p-8">
                    <div className="flex items-center justify-between mb-6">
                      <div>
                        <h2 className="text-xl font-black text-slate-900">{triggerNode.data.config?.form_title || 'Form Trigger'}</h2>
                        <p className="text-sm text-slate-500 mt-1">{triggerNode.data.config?.form_description || 'Fill out the form to trigger the workflow.'}</p>
                      </div>
                      <button
                        onClick={() => {
                          setShowTriggerForm(false);
                          setTriggerFormData({});
                          setTriggerFormErrors({});
                          setTriggerNode(null);
                        }}
                        className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400 hover:text-slate-600"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                      </button>
                    </div>

                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        if (!isPollingEnabled) {
                          toast.error(WORKFLOW_INACTIVE_ERROR_MESSAGE);
                          return;
                        }
                        const formFields = Array.isArray(triggerNode.data.config?.fields) ? triggerNode.data.config.fields : [];
                        const submittedValues = readFormValuesFromElement(e.currentTarget as HTMLFormElement, formFields, triggerFormData);
                        setTriggerFormData(submittedValues);
                        const validationErrors = validateFormValues(formFields, submittedValues);
                        setTriggerFormErrors(validationErrors);
                        if (Object.keys(validationErrors).length > 0) {
                          toast.error('Please fix the highlighted fields.');
                          return;
                        }
                        const runtimeLoopOverride = resolveRuntimeLoopOverride();
                        if (runtimeLoopOverride === 'cancelled') {
                          return;
                        }
                        try {
                          const enqueue = await executionService.runWorkflowForm(workflowId, {
                            form_data: submittedValues,
                            start_node_id: triggerNode.id,
                            loop_control_override: runtimeLoopOverride || undefined,
                          });
                          toast.success('Workflow execution started!');
                          setShowTriggerForm(false);
                          setTriggerFormData({});
                          setTriggerFormErrors({});
                          setTriggerNode(null);
                          beginExecutionTracking(enqueue.execution_id);
                        } catch (error) {
                          console.error('Form submission failed:', error);
                          const message = toUserFriendlyErrorMessage(
                            (error as any)?.response?.data?.detail,
                            'Failed to start workflow execution',
                          );
                          toast.error(message);
                        }
                      }}
                      className="space-y-6"
                    >
                      {Array.isArray(triggerNode.data.config?.fields) && triggerNode.data.config.fields.length > 0 ? (
                        <FormFieldRenderer
                          fields={triggerNode.data.config.fields}
                          values={triggerFormData}
                          errors={triggerFormErrors}
                          onChange={(key, value) => {
                            setTriggerFormData(prev => ({ ...prev, [key]: value }));
                            setTriggerFormErrors(prev => ({ ...prev, [key]: '' }));
                          }}
                        />
                      ) : (
                        <div className="text-center py-8 text-slate-500">
                          <p>No form fields configured. Add fields in the trigger node configuration.</p>
                        </div>
                      )}

                      <div className="flex justify-end gap-3 pt-4">
                        <button
                          type="button"
                          onClick={() => {
                            setShowTriggerForm(false);
                            setTriggerFormData({});
                            setTriggerFormErrors({});
                            setTriggerNode(null);
                          }}
                          className="px-6 py-2.5 text-sm font-bold text-slate-600 hover:text-slate-800 transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl transition-colors"
                        >
                          Submit & Run Workflow
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
            )}

            {selectedNode && (
              <ConfigPanel
                node={selectedNode as WorkflowNode}
                workflowId={workflowId}
                isWorkflowActive={isPollingEnabled}
                upstreamData={upstreamData}
                previousNodes={previousNodes}
                nextNodes={nextNodes}
                onClose={() => setSelectedNodeId(null)}
                onUpdate={updateNodeConfig}
                onUpdateLabel={updateNodeLabel}
                onNavigateNode={(nodeId) => setSelectedNodeId(nodeId)}
                onExecutionEnqueued={({ executionId, nodeId, triggeredBy }) => {
                  beginExecutionTracking(executionId, {
                    triggeredBy,
                    primeNodeId: nodeId,
                  });
                }}
              />
            )}
          </ReactFlow>
        </div>
      </ReactFlowProvider>
      ) : activeTab === 'executions' ? (
        <div className="flex-1 overflow-y-auto p-6 pt-20">
          <div className="max-w-4xl mx-auto space-y-6">
            <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
              <div className="flex items-center justify-between gap-10 mb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Execution history</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">Track every workflow run and its duration.</p>
                </div>
                <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
                  {executionHistory.length} run{executionHistory.length === 1 ? '' : 's'}
                </span>
              </div>

              {executionHistory.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
                  No executions recorded yet. Run the workflow to populate history.
                </div>
              ) : (
                <div className="space-y-4">
                  {executionHistory.map((run) => (
                    <div key={run.executionId} className="space-y-2">
                      <button
                        type="button"
                        onClick={() => handleExecutionRowClick(run.executionId)}
                        className={`group relative w-full text-left rounded-2xl border p-5 transition-colors grid grid-cols-1 md:grid-cols-[1fr_auto] gap-4 items-center shadow-sm hover:shadow-md ${
                          selectedExecutionId === run.executionId
                            ? 'border-blue-400 bg-blue-50/40 dark:bg-blue-500/10 ring-2 ring-blue-500/20'
                            : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                        }`}
                      >
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 items-center">
                          <div>
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Started</div>
                            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{formatDateTime(run.startedAt)}</div>
                          </div>

                          <div>
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Finished</div>
                            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{formatDateTime(run.finishedAt)}</div>
                          </div>
                          
                          <div>
                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Duration</div>
                            <div className="text-sm font-bold text-slate-800 dark:text-slate-100">{run.durationMs != null ? `${(run.durationMs / 1000).toFixed(2)}s` : <span className="text-blue-500 animate-pulse">Running...</span>}</div>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 justify-between md:justify-end border-t md:border-t-0 border-slate-100 dark:border-slate-800 pt-4 md:pt-0">
                          <span className={`inline-flex items-center rounded-full px-3 py-1.5 text-[10px] font-black tracking-widest uppercase shadow-sm ${getStatusBadgeClasses(run.status)}`}>
                            {run.status}
                          </span>
                          <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            {run.triggeredBy}
                          </span>
                        </div>
                      </button>

                      {selectedExecutionId === run.executionId && (
                        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/30 p-4">
                          {isExecutionDetailLoading && (
                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-5 text-sm text-slate-500 dark:text-slate-400">
                              Loading node execution logs...
                            </div>
                          )}

                          {executionDetailError && !isExecutionDetailLoading && (
                            <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-900/20 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                              {executionDetailError}
                            </div>
                          )}

                          {!isExecutionDetailLoading && selectedExecutionDetail && selectedExecutionDetail.id === run.executionId && (
                            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
                              {selectedExecutionDetail.loop_settings && (
                                <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/60">
                                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">
                                    Effective Loop Settings
                                  </div>
                                  <div className="text-[12px] font-mono text-slate-700 dark:text-slate-300 flex flex-wrap gap-x-5 gap-y-1">
                                    <span><span className="text-slate-400 dark:text-slate-500">enabled</span> {String(selectedExecutionDetail.loop_settings.enabled)}</span>
                                    <span><span className="text-slate-400 dark:text-slate-500">max_node</span> {selectedExecutionDetail.loop_settings.max_node_executions}</span>
                                    <span><span className="text-slate-400 dark:text-slate-500">max_total</span> {selectedExecutionDetail.loop_settings.max_total_node_executions}</span>
                                    <span><span className="text-slate-400 dark:text-slate-500">source</span> {selectedExecutionDetail.loop_settings.source === 'runtime_override' ? 'Runtime Override' : 'Workflow Default'}</span>
                                  </div>
                                </div>
                              )}
                              <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                                Node Execution Logs
                              </div>
                              <div className="max-h-[320px] overflow-y-auto">
                                {selectedExecutionDetail.node_results.map((nodeResult) => (
                                  <div
                                    key={`${selectedExecutionDetail.id}_${nodeResult.node_id}`}
                                    className="px-4 py-3 border-b last:border-b-0 border-slate-100 dark:border-slate-800 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2"
                                  >
                                    <div>
                                      <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                                        {nodeResult.node_type}
                                        <span className="ml-2 text-xs font-mono text-slate-400 dark:text-slate-500">{nodeResult.node_id}</span>
                                      </div>
                                      {nodeResult.error_message && (
                                        <div className="mt-1 text-xs text-rose-600 dark:text-rose-300 font-mono whitespace-pre-wrap break-words">
                                          {toUserFriendlyErrorMessage(nodeResult.error_message, '')}
                                        </div>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-black tracking-widest uppercase ${getStatusBadgeClasses(nodeResult.status)}`}>
                                        {nodeResult.status}
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-6 pt-20">
          <div className="max-w-4xl mx-auto space-y-6">
            <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
              <div className="flex items-center justify-between gap-6 mb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Version history</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">Preview and restore saved workflow versions.</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
                    {workflowVersions.length} version{workflowVersions.length === 1 ? '' : 's'}
                  </span>
                  <button
                    type="button"
                    onClick={() => void loadWorkflowVersions()}
                    disabled={isVersionsLoading || !workflowId || workflowId === 'new'}
                    className="rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Refresh
                  </button>
                </div>
              </div>

              {!workflowId || workflowId === 'new' ? (
                <div className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
                  Save this workflow once to start creating and restoring versions.
                </div>
              ) : isVersionsLoading ? (
                <div className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
                  Loading versions...
                </div>
              ) : workflowVersions.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 p-8 text-center text-slate-500 dark:text-slate-400">
                  No versions yet. Use Save + Create Version to add your first snapshot.
                </div>
              ) : (
                <div className="space-y-3">
                  {versionsError && (
                    <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-900/20 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                      {versionsError}
                    </div>
                  )}

                  {workflowVersions.map((version) => {
                    const isCurrent = currentVersionId === version.id;
                    const isPreviewing = versionPreviewMeta?.versionId === version.id;
                    return (
                      <div
                        key={version.id}
                        className={`rounded-2xl border p-4 transition ${
                          isPreviewing
                            ? 'border-cyan-400 bg-cyan-50/50 dark:bg-cyan-500/10'
                            : isCurrent
                              ? 'border-emerald-300 bg-emerald-50/40 dark:bg-emerald-500/10'
                              : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50'
                        }`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100">
                                Version v{version.version_number}
                              </h4>
                              {isCurrent && (
                                <span className="rounded-full bg-emerald-100 dark:bg-emerald-900/40 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                                  Current
                                </span>
                              )}
                              {isPreviewing && (
                                <span className="rounded-full bg-cyan-100 dark:bg-cyan-900/40 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider text-cyan-700 dark:text-cyan-300">
                                  Previewing
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                              Created {formatDateTime(version.created_at || null)}
                            </p>
                            {version.note && (
                              <p className="mt-2 text-xs text-slate-700 dark:text-slate-300">
                                {version.note}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void previewWorkflowVersion(version.id)}
                              disabled={isVersionDetailLoading}
                              className="rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              Preview
                            </button>
                            {!isCurrent && (
                              <button
                                type="button"
                                onClick={() => void restoreWorkflowVersion(version.id)}
                                className="rounded-xl bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                              >
                                Restore Workflow
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {selectedVersionId && (
              <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6">
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Selected version preview</h3>
                {isVersionDetailLoading ? (
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Loading version snapshot...</p>
                ) : selectedVersionDetail && selectedVersionDetail.id === selectedVersionId ? (
                  <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                    <p>
                      <span className="font-semibold text-slate-800 dark:text-slate-100">Name:</span>{' '}
                      {selectedVersionDetail.snapshot_json?.name || 'Untitled Workflow'}
                    </p>
                    <p>
                      <span className="font-semibold text-slate-800 dark:text-slate-100">Description:</span>{' '}
                      {selectedVersionDetail.snapshot_json?.description || 'No description'}
                    </p>
                    <p>
                      <span className="font-semibold text-slate-800 dark:text-slate-100">Nodes:</span>{' '}
                      {selectedVersionDetail.snapshot_json?.definition?.nodes?.length || 0}
                    </p>
                    <p>
                      <span className="font-semibold text-slate-800 dark:text-slate-100">Edges:</span>{' '}
                      {selectedVersionDetail.snapshot_json?.definition?.edges?.length || 0}
                    </p>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    Select a version to load its snapshot details.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkflowCanvas;
