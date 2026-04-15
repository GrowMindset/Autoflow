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
import toast from 'react-hot-toast';
import { useTheme } from '../../context/ThemeContext';
import { Play, LayoutGrid, Sparkles, Search, Undo2, Redo2, Loader2, Plus } from 'lucide-react';

const nodeTypes = {
  trigger: BaseNode,
  action: BaseNode,
  transform: BaseNode,
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
const EXECUTION_POLL_INTERVAL_MS = 700;
const UNDO_REDO_HISTORY_LIMIT = 100;
const UNDO_REDO_COMMIT_DEBOUNCE_MS = 180;
const AI_APPLY_PROCESS_MS = 950;
const AI_APPLY_HIGHLIGHT_MS = 2200;
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
  };
  signature: string;
}

interface AiPreviewGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  name: string;
}

interface WorkflowCanvasProps {
  workflowId: string;
  footerOffset?: number;
  onExecutionStart?: (executionId: string) => void;
  onExecutionUpdate?: (detail: ExecutionDetail) => void;
  onToggleAiAssistant?: () => void;
  isAiAssistantOpen?: boolean;
  onCanvasMutated?: (reason: string) => void;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  workflowId,
  footerOffset = 0,
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
  const [nodes, setNodes, onNodesChangeBase] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<WorkflowEdge>(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const { isDark } = useTheme();
  const [activeTab, setActiveTab] = useState<'editor' | 'executions'>('editor');
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistoryEntry[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [selectedExecutionDetail, setSelectedExecutionDetail] = useState<ExecutionDetail | null>(null);
  const [isExecutionDetailLoading, setIsExecutionDetailLoading] = useState(false);
  const [executionDetailError, setExecutionDetailError] = useState<string | null>(null);
  const isHydratingCanvasRef = useRef(false);
  const isApplyingHistoryRef = useRef(false);
  const executionDetailCacheRef = useRef<Record<string, ExecutionDetail>>({});
  const executionDetailRequestIdRef = useRef(0);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const historyStackRef = useRef<CanvasHistoryEntry[]>([]);
  const historyIndexRef = useRef(-1);
  const historyCommitTimeoutRef = useRef<number | null>(null);
  const aiApplyTimeoutRef = useRef<number | null>(null);
  const aiHighlightTimeoutRef = useRef<number | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [isAiApplyingChanges, setIsAiApplyingChanges] = useState(false);
  const [recentAiNodeIds, setRecentAiNodeIds] = useState<string[]>([]);
  const [recentAiEdgeIds, setRecentAiEdgeIds] = useState<string[]>([]);

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
          return nextConfig;
        })(),
        id: node.id,
        type: node.data.type,
        label: node.data.label,
        position: node.position,
      })),
      edges: sourceEdges.map((edge: any) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle,
        targetHandle: edge.targetHandle,
        branch: edge.branch ?? edge.sourceHandle ?? undefined,
      })),
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
    if (!iso) return '—';
    return new Intl.DateTimeFormat('default', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso));
  };

  const getStatusBadgeClasses = (status: string) => {
    if (status === 'SUCCEEDED') {
      return 'bg-emerald-100/80 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/20';
    }
    if (status === 'FAILED') {
      return 'bg-rose-100/80 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border border-rose-200/50 dark:border-rose-500/20';
    }
    if (status === 'RUNNING') {
      return 'bg-purple-100/80 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400 border border-purple-200/50 dark:border-purple-500/20';
    }
    return 'bg-slate-100/80 text-slate-700 dark:bg-slate-500/20 dark:text-slate-400 border border-slate-200/50 dark:border-slate-500/20';
  };

  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [nodes, edges]);

  useEffect(() => {
    clearPendingHistoryCommit();
    clearAiApplyTimers();
    historyStackRef.current = [];
    historyIndexRef.current = -1;
    setCanUndo(false);
    setCanRedo(false);
    setIsAiApplyingChanges(false);
    setRecentAiNodeIds([]);
    setRecentAiEdgeIds([]);
    setAiPreviewGraph(null);
    setSelectedExecutionId(null);
    setSelectedExecutionDetail(null);
    setExecutionDetailError(null);
    setIsExecutionDetailLoading(false);
    executionDetailCacheRef.current = {};
    executionDetailRequestIdRef.current = 0;
    setHasPickedNewWorkflowStarter(false);
  }, [workflowId, clearPendingHistoryCommit, clearAiApplyTimers]);

  useEffect(() => {
    if (workflowId === 'new') {
      setExecutionHistory([]);
      return;
    }

    const fetchExecutions = async () => {
      try {
        const response = await executionService.listExecutions(workflowId);
        if (response && response.executions) {
          const formattedHistory = response.executions.map((exe: any) => ({
            executionId: exe.id,
            status: exe.status,
            triggeredBy: exe.triggered_by || 'manual',
            startedAt: exe.started_at,
            finishedAt: exe.finished_at,
            errorMessage: exe.error_message || null,
            durationMs: exe.started_at && exe.finished_at
              ? Date.parse(exe.finished_at) - Date.parse(exe.started_at)
              : undefined
          }));
          setExecutionHistory(formattedHistory);
        }
      } catch (error) {
        console.error('Failed to fetch execution history:', error);
      }
    };

    fetchExecutions();
  }, [workflowId]);

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
      const message = error?.response?.data?.detail || 'Failed to load execution detail';
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

  // Alignment Detection
  const [isAligned, setIsAligned] = useState(true);

  // Execution State
  const pollingIntervalRef = useRef<number | null>(null);
  const activeExecutionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const handleQuickAdd = (e: any) => {
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
      setMenuPosition(position);
      setMenuVisible(true);
    };

    window.addEventListener('rf-quick-add', handleQuickAdd);
    return () => {
      window.removeEventListener('rf-quick-add', handleQuickAdd);
      setMenuSearchTerm('');
    };
  }, [isAiPreviewMode, nodes, reactFlowInstance]);

  useEffect(() => {
    if (menuVisible && menuSearchRef.current) {
      setTimeout(() => menuSearchRef.current?.focus(), 50);
    } else if (!menuVisible) {
      setMenuSearchTerm('');
    }
  }, [menuVisible]);

  const [showTriggerForm, setShowTriggerForm] = useState(false);
  const [triggerFormData, setTriggerFormData] = useState<Record<string, string>>({});
  const [triggerNode, setTriggerNode] = useState<WorkflowNode | null>(null);

  const emitCanvasMutation = useCallback((reason: string) => {
    if (isHydratingCanvasRef.current || isApplyingHistoryRef.current) return;
    scheduleHistorySnapshot();
    onCanvasMutated?.(reason);
  }, [onCanvasMutated, scheduleHistorySnapshot]);

  const onNodesChange = useCallback((changes: any[]) => {
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
  }, [onNodesChangeBase, emitCanvasMutation]);

  const onEdgesChange = useCallback((changes: any[]) => {
    onEdgesChangeBase(changes);

    if (isHydratingCanvasRef.current) return;
    const hasMeaningfulChange = changes.some((change) =>
      ['add', 'remove', 'reset'].includes(change?.type)
    );
    if (hasMeaningfulChange) {
      emitCanvasMutation('edges_change');
    }
  }, [onEdgesChangeBase, emitCanvasMutation]);

  useEffect(() => {
    const misaligned = nodes.some(
      (node) => node.position.x % 20 !== 0 || node.position.y % 20 !== 0
    );
    setIsAligned(!misaligned);
  }, [nodes]);

  // Update edges to show status animations path-aware
  useEffect(() => {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));

    const isEdgeOnSelectedBranch = (edge: any, sourceNode: WorkflowNode | undefined): boolean => {
      if (!sourceNode) return false;

      const sourceStatus = sourceNode.data.status;
      if (sourceStatus !== 'RUNNING' && sourceStatus !== 'SUCCEEDED') {
        return false;
      }

      if (sourceStatus === 'RUNNING') {
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

      return String(edge.sourceHandle) === String(chosenBranch);
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
        } else if (sourceNode?.data.status === 'RUNNING' && isOnSelectedPath) {
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
  }, [nodes, setEdges]);

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
          NODE_LIBRARY.transform.some(ref => ref.type === n.type) ? 'transform' : 'ai';
      return {
        ...n,
        data: {
          label: n.label || n.type,
          config: n.config || {},
          type: n.type,
          category,
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

    const graphEdges: WorkflowEdge[] = (definition?.edges || []).map((e: any, index: number) => ({
      ...e,
      id: e.id || `e_${e.source}_${e.target}_${index}`,
      type: 'deletable',
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    }));

    return {
      nodes: graphNodes,
      edges: graphEdges,
      name: typeof definition?.name === 'string' ? definition.name : '',
    };
  }, [autoLayout]);

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
    if (isAiPreviewMode) {
      toast('Accept or discard the AI preview before aligning nodes.', { icon: 'ℹ️' });
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
  }, [isAiPreviewMode, nodes, edges, setNodes, autoLayout, reactFlowInstance, emitCanvasMutation]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current !== null) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const pollExecution = useCallback(async (executionId: string) => {
    if (activeExecutionIdRef.current !== executionId) {
      return;
    }

    try {
      const detail = await executionService.getExecution(executionId);
      if (activeExecutionIdRef.current !== executionId) {
        return;
      }

      // Update nodes with their execution status and results
      setNodes((nds) =>
        nds.map((node) => {
          const result = detail.node_results.find((r) => r.node_id === node.id);
          if (result) {
            return {
              ...node,
              data: {
                ...node.data,
                status: result.status,
                last_execution_result: result
              }
            };
          }
          return node;
        })
      );
      setExecutionHistory((history) =>
        history.map((entry) =>
          entry.executionId === executionId
            ? {
              ...entry,
              status: detail.status,
              errorMessage: detail.error_message,
              startedAt: detail.started_at,
              finishedAt: detail.finished_at,
              durationMs:
                detail.started_at && detail.finished_at
                  ? Date.parse(detail.finished_at) - Date.parse(detail.started_at)
                  : entry.durationMs,
            }
            : entry
        )
      );
      executionDetailCacheRef.current[executionId] = detail;
      if (selectedExecutionId === executionId) {
        setSelectedExecutionDetail(detail);
      }
      onExecutionUpdate?.(detail);

      if (detail.status === 'SUCCEEDED' || detail.status === 'FAILED') {
        stopPolling();
        activeExecutionIdRef.current = null;
        if (detail.status === 'SUCCEEDED') {
          toast.success('Workflow finished successfully');
        } else {
          toast.error(`Workflow failed: ${detail.error_message || 'Unknown error'}`);
        }
      }
    } catch (error) {
      console.error('Polling failed:', error);
      stopPolling();
    }
  }, [onExecutionUpdate, selectedExecutionId, setNodes, stopPolling]);

  const beginExecutionTracking = useCallback((executionId: string) => {
    stopPolling();
    activeExecutionIdRef.current = executionId;
    onExecutionStart?.(executionId);
    setExecutionHistory((history) => [
      {
        executionId,
        status: 'PENDING',
        triggeredBy: 'manual',
        startedAt: null,
        finishedAt: null,
        errorMessage: null,
      },
      ...history,
    ]);
    void pollExecution(executionId);
    pollingIntervalRef.current = window.setInterval(() => {
      void pollExecution(executionId);
    }, EXECUTION_POLL_INTERVAL_MS);
  }, [onExecutionStart, pollExecution, stopPolling]);

  useEffect(() => {
    const onFormExecutionStarted = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;

      const payload = event.data as {
        type?: string;
        workflowId?: string;
        executionId?: string;
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
      beginExecutionTracking(payload.executionId);
      toast.success('Form submitted. Workflow execution started.');
    };

    window.addEventListener('message', onFormExecutionStarted);
    return () => window.removeEventListener('message', onFormExecutionStarted);
  }, [workflowId, beginExecutionTracking, setNodes]);

  const handleRunWorkflow = useCallback(async () => {
    if (isAiPreviewMode) {
      toast('Accept or discard the AI preview before executing workflow.', { icon: 'ℹ️' });
      return;
    }

    if (workflowId === 'new') {
      toast.error('Please save your workflow before running');
      return;
    }

    const triggerTypes = ['manual_trigger', 'form_trigger', 'webhook_trigger', 'workflow_trigger'];
    const triggerCandidates = nodes.filter(node => {
      return triggerTypes.includes(node.data.type) || node.type === 'trigger';
    });
    const rootTriggers = triggerCandidates.filter(node => !edges.some(edge => edge.target === node.id));

    if (rootTriggers.length === 0) {
      if (triggerCandidates.length === 0) {
        toast.error('No trigger nodes found in workflow. Please add a Manual Trigger, Form Trigger, Webhook Trigger, or Workflow Trigger node.');
        return;
      }

      if (triggerCandidates.length === 1) {
        toast('Trigger node has incoming connections, but execution will continue using the single available trigger. Make sure trigger nodes have no incoming edges.', { icon: '⚠️' });
        const trigger = triggerCandidates[0];
        // Reset status of all nodes before starting
        setNodes((nds) =>
          nds.map((node) => ({
            ...node,
            data: { ...node.data, status: 'PENDING', last_execution_result: null }
          }))
        );

        try {
          if (trigger.data.type === 'manual_trigger') {
            const enqueue = await executionService.runWorkflow(workflowId);
            toast.success('Workflow execution started!');
            beginExecutionTracking(enqueue.execution_id);
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
          } else {
            toast.error(`Unsupported trigger type: ${trigger.data.type}`);
          }
        } catch (error) {
          console.error('Execution failed:', error);
          toast.error('Workflow execution failed. Check console for details.');
        }
        return;
      }

      toast.error('All trigger nodes have incoming connections. Trigger nodes should not have any incoming edges.');
      return;
    }

    if (rootTriggers.length > 1) {
      toast.error('Multiple trigger nodes found. Please ensure only one trigger node exists.');
      return;
    }

    const trigger = rootTriggers[0];

    // Reset status of all nodes before starting
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: { ...node.data, status: 'PENDING', last_execution_result: null }
      }))
    );

    try {
      if (trigger.data.type === 'manual_trigger') {
        const enqueue = await executionService.runWorkflow(workflowId);
        toast.success('Workflow execution started!');
        beginExecutionTracking(enqueue.execution_id);
      } else if (trigger.data.type === 'form_trigger') {
        const formUrl = buildFormPageUrl(workflowId, trigger.id);
        const opened = window.open(formUrl, '_blank');
        if (opened) {
          toast.success('Form opened in a new tab. Submit there to continue execution.');
        } else {
          toast(`Popup blocked. Open this form URL manually: ${formUrl}`, { duration: 7000 });
        }
      } else if (trigger.data.type === 'webhook_trigger') {
        // For webhook triggers, show information about webhook usage
        const method = String(trigger.data?.config?.method || 'POST').toUpperCase();
        toast.success(`Webhook trigger: Use HTTP ${method} to the webhook endpoint to trigger this workflow`, { duration: 5000 });
      } else {
        toast.error(`Unsupported trigger type: ${trigger.data.type}`);
      }
    } catch (error) {
      console.error('Execution failed:', error);
      toast.error('Workflow execution failed. Check console for details.');
    }
  }, [isAiPreviewMode, workflowId, nodes, edges, beginExecutionTracking]);

  useEffect(() => {
    stopPolling();
    activeExecutionIdRef.current = null;
    return () => {
      stopPolling();
      activeExecutionIdRef.current = null;
    };
  }, [workflowId, stopPolling]);

  const isValidConnection = useCallback((connection: Connection) => {
    // Only allow one connection per source handle
    const existingEdge = edges.find(
      (edge) => edge.source === connection.source && edge.sourceHandle === connection.sourceHandle
    );
    return !existingEdge;
  }, [edges]);

  const onConnect = useCallback((params: Connection) => {
    if (isAiPreviewMode) return;
    if (!params.source || !params.target) return;

    const newEdge: WorkflowEdge = {
      ...params,
      source: params.source,
      target: params.target,
      sourceHandle: params.sourceHandle,
      targetHandle: params.targetHandle,
      branch: params.sourceHandle ?? undefined,
      id: `e_${params.source}_${params.target}_${params.sourceHandle || 'def'}_${Date.now()}`,
      type: 'deletable',
      animated: false,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' }
    };
    setEdges((eds) => addEdge(newEdge as any, eds));
    emitCanvasMutation('connect_nodes');
    connectingNode.current = null; // Clear connection state after successful connection
    toast.success('Nodes connected');
  }, [isAiPreviewMode, setEdges, emitCanvasMutation]);

  const onConnectStart = useCallback((_: any, {
    nodeId,
    handleId,
    handleType,
  }: {
    nodeId: string | null;
    handleId?: string | null;
    handleType?: 'source' | 'target' | null;
  }) => {
    if (isAiPreviewMode) {
      connectingNode.current = null;
      return;
    }
    if (!nodeId) {
      connectingNode.current = null;
      return;
    }
    connectingNode.current = {
      nodeId,
      handleId: handleId ?? null,
      connectionType: handleType === 'target' ? 'target' : 'source',
    };
  }, [isAiPreviewMode]);

  const onConnectEnd = useCallback(
    (event: any) => {
      if (isAiPreviewMode) return;
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
    [isAiPreviewMode, reactFlowInstance]
  );

  const onPaneClick = useCallback(() => {
    setMenuVisible(false);
    connectingNode.current = null; // Clear connection state when clicking on pane
  }, []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      if (isAiPreviewMode) {
        toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
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
    [isAiPreviewMode, reactFlowInstance]
  );

  const addNodeAtPosition = useCallback((type: string, position: XYPosition) => {
    if (isAiPreviewMode) {
      toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
      return;
    }
    try {
      const newNode = createNode(type, position);
      const newNodeId = newNode.id;

      setNodes((nds) => nds.concat(newNode));
      emitCanvasMutation('add_node');
      toast.success(`${newNode.data.label} added`);

      if (connectingNode.current) {
        const { nodeId: anchorNodeId, handleId, connectionType } = connectingNode.current;
        const sourceHandle = handleId ?? undefined;
        const newEdge: WorkflowEdge =
          connectionType === 'target'
            ? {
                id: `e_${newNodeId}_${anchorNodeId}_${handleId || 'def'}`,
                source: newNodeId,
                target: anchorNodeId,
                sourceHandle: null,
                targetHandle: handleId ?? null,
                branch: undefined,
                type: 'deletable',
                animated: true,
                style: { stroke: '#94a3b8', strokeWidth: 2 },
                markerEnd: {
                  type: MarkerType.ArrowClosed,
                  color: '#94a3b8',
                },
              }
            : {
                id: `e_${anchorNodeId}_${newNodeId}_${handleId || 'def'}`,
                source: anchorNodeId,
                target: newNodeId,
                sourceHandle,
                targetHandle: null,
                branch: sourceHandle ?? undefined,
                type: 'deletable',
                animated: true,
                style: { stroke: '#94a3b8', strokeWidth: 2 },
                markerEnd: {
                  type: MarkerType.ArrowClosed,
                  color: '#94a3b8',
                },
              };
        setEdges((eds) => addEdge(newEdge, eds));
        emitCanvasMutation('quick_add_connect');
        connectingNode.current = null;
      }

      setMenuVisible(false);
    } catch (error) {
      console.error(error);
    }
  }, [isAiPreviewMode, setNodes, setEdges, emitCanvasMutation]);

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: any) => {
    if (isAiPreviewMode) return;
    setSelectedNodeId(node.id);
  }, [isAiPreviewMode]);

  const openQuickAddAtCenter = useCallback(() => {
    if (!reactFlowInstance || !reactFlowWrapper.current) return;
    const rect = reactFlowWrapper.current.getBoundingClientRect();
    const centerPosition = reactFlowInstance.screenToFlowPosition({
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
    connectingNode.current = null;
    setMenuPosition(centerPosition);
    setMenuVisible(true);
  }, [reactFlowInstance]);

  const handleAddFirstStepFromStarter = useCallback(() => {
    setHasPickedNewWorkflowStarter(true);
    if (typeof (window as any).openNodePalette === 'function') {
      (window as any).openNodePalette();
      return;
    }
    openQuickAddAtCenter();
  }, [openQuickAddAtCenter]);

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
    const incomingNodeCount = Array.isArray(definition.nodes) ? definition.nodes.length : 0;
    const incomingEdgeCount = Array.isArray(definition.edges) ? definition.edges.length : 0;
    if (workflowId === 'new' && incomingNodeCount === 0 && incomingEdgeCount === 0) {
      setHasPickedNewWorkflowStarter(false);
    }

    // Map simplified nodes back to React Flow format
    const rfNodes: WorkflowNode[] = (definition.nodes || []).map((n: any) => {
      const category = NODE_LIBRARY.trigger.some(ref => ref.type === n.type) ? 'trigger' :
        NODE_LIBRARY.action.some(ref => ref.type === n.type) ? 'action' :
          NODE_LIBRARY.transform.some(ref => ref.type === n.type) ? 'transform' : 'ai';

      return {
        id: n.id,
        type: category,
        position: n.position,
        data: {
          label: n.label,
          config: n.config,
          type: n.type,
          category: category
        }
      };
    });

    isHydratingCanvasRef.current = true;
    setNodes(rfNodes);

    // Map simplified edges back to React Flow format with handle awareness
    const rfEdges = (definition.edges || []).map((e: any) => ({
      ...e,
      type: 'deletable',
      sourceHandle: e.sourceHandle || e.branch || null,
      targetHandle: e.targetHandle || null,
      animated: false,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
    }));

    setEdges(rfEdges);
    if (options?.resetHistory !== false) {
      resetUndoRedoHistory({
        nodes: (definition.nodes || []).map((node: any) => ({
          id: node.id,
          type: node.type,
          label: node.label,
          position: node.position,
          config: node.config || {},
        })),
        edges: (definition.edges || []).map((edge: any) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle || edge.branch || null,
          targetHandle: edge.targetHandle || null,
          branch: edge.branch ?? edge.sourceHandle ?? undefined,
        })),
      });
    }

    requestAnimationFrame(() => {
      isHydratingCanvasRef.current = false;
    });
  }, [setNodes, setEdges, resetUndoRedoHistory, workflowId]);

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

      if (isUndo) {
        event.preventDefault();
        undoCanvas();
      } else if (isRedo) {
        event.preventDefault();
        redoCanvas();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undoCanvas, redoCanvas]);

  useEffect(() => {
    return () => {
      clearPendingHistoryCommit();
      clearAiApplyTimers();
    };
  }, [clearPendingHistoryCommit, clearAiApplyTimers]);

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
      const graph = buildAiGraphFromDefinition(definition);
      applyAiGraphToCanvas(graph);
    };
    (window as any).previewAiWorkflow = (definition: any, options?: { name?: string }) => {
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
    (window as any).isCanvasDirty = () => isDirty;
    (window as any).undoCanvas = undoCanvas;
    (window as any).redoCanvas = redoCanvas;

    (window as any).addNodeAtCenter = (type: string) => {
      if (aiPreviewGraph) {
        toast('Accept or discard the AI preview before editing.', { icon: 'ℹ️' });
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
    addNodeAtPosition,
    applyAiGraphToCanvas,
    buildAiGraphFromDefinition,
  ]);

  const updateNodeConfig = useCallback((id: string, config: Record<string, any>, output?: any) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return {
            ...node,
            data: {
              ...node.data,
              config,
              last_output: output || node.data.last_output
            },
          };
        }
        return node;
      })
    );
    emitCanvasMutation('node_config_change');
  }, [setNodes, emitCanvasMutation]);

  const getUpstreamData = (nodeId: string) => {
    const upstreamEdges = edges.filter(e => e.target === nodeId) as WorkflowEdge[];
    if (upstreamEdges.length === 0) return null;

    const combinedData: Record<string, any> = {};
    upstreamEdges.forEach(edge => {
      const sourceNode = nodes.find(n => n.id === edge.source);
      if (sourceNode?.data.last_output) {
        Object.assign(combinedData, sourceNode.data.last_output);
      } else {
        const mockMap: Record<string, any> = {
          manual_trigger: { body: { message: "Hello world" }, user: { id: "u_123", name: "Ishika" } },
          webhook_trigger: { query: { id: 50 }, headers: { "Content-Type": "application/json" } },
          form_trigger: { submission: { name: "Test User", email: "test@example.com", priority: "high" } },
          filter: { items: [{ id: 1, name: "A" }, { id: 2, name: "B" }] },
          aggregate: { result: 500, count: 2 }
        };
        const typeMatch = sourceNode?.data.type || 'manual_trigger';
        Object.assign(combinedData, mockMap[typeMatch as string] || mockMap.manual_trigger);
      }
    });

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

  const selectedNode = isAiPreviewMode ? null : nodes.find(n => n.id === selectedNodeId);
  const upstreamData = isAiPreviewMode ? null : (selectedNodeId ? getUpstreamData(selectedNodeId) : null);
  const previousNodes = useMemo(() => {
    if (isAiPreviewMode) return [] as WorkflowNode[];
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
  }, [isAiPreviewMode, selectedNodeId, edges, getNodeById, sortNavigationNodes]);

  const nextNodes = useMemo(() => {
    if (isAiPreviewMode) return [] as WorkflowNode[];
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
  }, [isAiPreviewMode, selectedNodeId, edges, getNodeById, sortNavigationNodes]);

  const graphNodes = aiPreviewGraph?.nodes || nodes;
  const graphEdges = aiPreviewGraph?.edges || edges;
  const recentAiNodeIdSet = useMemo(() => new Set(recentAiNodeIds), [recentAiNodeIds]);
  const recentAiEdgeIdSet = useMemo(() => new Set(recentAiEdgeIds), [recentAiEdgeIds]);

  const displayNodes = useMemo(() => {
    if (recentAiNodeIdSet.size === 0) {
      return graphNodes;
    }

    return graphNodes.map((node) => {
      if (!recentAiNodeIdSet.has(node.id)) {
        return node;
      }
      const existingClass = node.className ? `${node.className} ` : '';
      return {
        ...node,
        className: `${existingClass}ai-node-updated`,
      };
    });
  }, [graphNodes, recentAiNodeIdSet]);

  const displayEdges = useMemo(() => {
    if (recentAiEdgeIdSet.size === 0) {
      return graphEdges;
    }

    return graphEdges.map((edge) => {
      if (!recentAiEdgeIdSet.has(edge.id)) {
        return edge;
      }
      return {
        ...edge,
        animated: true,
        style: {
          ...(edge.style || {}),
          stroke: '#3b82f6',
          strokeWidth: 2.6,
          strokeDasharray: '8 6',
        },
      };
    });
  }, [graphEdges, recentAiEdgeIdSet]);

  const showNewWorkflowStarter =
    activeTab === 'editor' &&
    workflowId === 'new' &&
    nodes.length === 0 &&
    !isAiPreviewMode &&
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
          <div className="text-xs text-slate-500 dark:text-slate-400 ml-3">
            {executionHistory.length > 0 ? `${executionHistory.length} execution${executionHistory.length > 1 ? 's' : ''} recorded` : 'No executions yet'}
          </div>
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
            onNodeDoubleClick={onNodeDoubleClick}
            onPaneClick={onPaneClick}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            deleteKeyCode={['Delete', 'Backspace']}
            nodesDraggable={!isAiPreviewMode}
            nodesConnectable={!isAiPreviewMode}
            elementsSelectable={!isAiPreviewMode}
            nodesFocusable={!isAiPreviewMode}
            edgesFocusable={!isAiPreviewMode}
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
                className="group flex items-center gap-3 bg-blue-600 hover:bg-blue-700 text-white px-7 py-3 rounded-2xl border border-blue-500 shadow-[0_20px_40px_rgba(37,99,235,0.3)] transition-all duration-300 active:scale-95"
              >
                <div className="relative">
                  <Play size={18} fill="currentColor" stroke="none" className="group-hover:scale-110 transition-transform" />
                  <div className="absolute inset-0 bg-white/20 rounded-full scale-150 opacity-0 group-hover:animate-ping" />
                </div>
                <span className="text-xs font-black uppercase tracking-[0.1em]">Execute Workflow</span>
              </button>
            </div>

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
                        <div className="text-[10px] font-bold uppercase text-slate-300 dark:text-slate-600 mb-2 ml-1 tracking-widest">{category}</div>
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
                                    category === 'transform' ? 'bg-amber-400' : 'bg-purple-400'
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
                        try {
                          const enqueue = await executionService.runWorkflowForm(workflowId, {
                            form_data: triggerFormData,
                          });
                          toast.success('Workflow execution started!');
                          setShowTriggerForm(false);
                          setTriggerFormData({});
                          setTriggerNode(null);
                          beginExecutionTracking(enqueue.execution_id);
                        } catch (error) {
                          console.error('Form submission failed:', error);
                          toast.error('Failed to start workflow execution');
                        }
                      }}
                      className="space-y-6"
                    >
                      {Array.isArray(triggerNode.data.config?.fields) && triggerNode.data.config.fields.length > 0 ? (
                        triggerNode.data.config.fields.map((field: any, index: number) => {
                          const fieldName = field?.name || `field_${index + 1}`;
                          const label = field?.label || fieldName;
                          const inputType = field?.type === 'textarea' ? 'textarea' : (field?.type || 'text');
                          const value = triggerFormData[fieldName] ?? '';

                          return (
                            <div key={`${fieldName}_${index}`} className="space-y-2">
                              <label className="text-sm font-bold text-slate-700">
                                {label}
                                {field?.required ? ' *' : ''}
                              </label>
                              {inputType === 'textarea' ? (
                                <textarea
                                  value={value}
                                  required={Boolean(field?.required)}
                                  onChange={(e) => setTriggerFormData(prev => ({ ...prev, [fieldName]: e.target.value }))}
                                  className="w-full min-h-[100px] rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:bg-white"
                                  placeholder={`Enter ${label.toLowerCase()}`}
                                />
                              ) : (
                                <input
                                  type={inputType}
                                  value={value}
                                  required={Boolean(field?.required)}
                                  onChange={(e) => setTriggerFormData(prev => ({ ...prev, [fieldName]: e.target.value }))}
                                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:bg-white"
                                  placeholder={`Enter ${label.toLowerCase()}`}
                                />
                              )}
                            </div>
                          );
                        })
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
                upstreamData={upstreamData}
                previousNodes={previousNodes}
                nextNodes={nextNodes}
                onClose={() => setSelectedNodeId(null)}
                onUpdate={updateNodeConfig}
                onNavigateNode={(nodeId) => setSelectedNodeId(nodeId)}
              />
            )}
          </ReactFlow>
        </div>
      </ReactFlowProvider>
      ) : (
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
                                          {nodeResult.error_message}
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
      )}
    </div>
  );
};

export default WorkflowCanvas;
