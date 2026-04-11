import React, { useCallback, useRef, useState, useEffect } from 'react';
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
} from 'reactflow';

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
import { Play, LayoutGrid } from 'lucide-react';

const nodeTypes = {
  trigger: BaseNode,
  action: BaseNode,
  transform: BaseNode,
  ai: BaseNode,
};

const edgeTypes = {
  deletable: DeletableEdge,
};

const initialNodes: WorkflowNode[] = [];
const initialEdges: WorkflowEdge[] = [];

interface ExecutionHistoryEntry {
  executionId: string;
  status: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationMs?: number;
}

interface WorkflowCanvasProps {
  workflowId: string;
  footerOffset?: number;
  onExecutionStart?: (executionId: string) => void;
  onExecutionUpdate?: (detail: ExecutionDetail) => void;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  workflowId,
  footerOffset = 0,
  onExecutionStart,
  onExecutionUpdate,
}) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const connectingNode = useRef<{ nodeId: string; handleId: string | null } | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<WorkflowEdge>(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const { isDark } = useTheme();
  const [activeTab, setActiveTab] = useState<'editor' | 'executions'>('editor');
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistoryEntry[]>([]);

  const formatDateTime = (iso: string | null) => {
    if (!iso) return '—';
    return new Intl.DateTimeFormat('default', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso));
  };

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
            startedAt: exe.started_at,
            finishedAt: exe.finished_at,
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

  // Quick Add State
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState<XYPosition | null>(null);

  // Config Panel State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Alignment Detection
  const [isAligned, setIsAligned] = useState(true);

  // Execution State
  const pollingIntervalRef = useRef<number | null>(null);
  const activeExecutionIdRef = useRef<string | null>(null);

  // Trigger Form Modal State
  const [showTriggerForm, setShowTriggerForm] = useState(false);
  const [triggerFormData, setTriggerFormData] = useState<Record<string, string>>({});
  const [triggerNode, setTriggerNode] = useState<WorkflowNode | null>(null);

  useEffect(() => {
    const misaligned = nodes.some(
      (node) => node.position.x % 20 !== 0 || node.position.y % 20 !== 0
    );
    setIsAligned(!misaligned);
  }, [nodes]);

  // Update edges to show status animations path-aware
  useEffect(() => {
    setEdges((eds) =>
      eds.map((edge) => {
        const sourceNode = nodes.find(n => n.id === edge.source);
        const status = sourceNode?.data.status;
        const result = sourceNode?.data.last_execution_result;
        
        let shouldAnimate = false;
        let isActivePath = false;

        if (status === 'RUNNING') {
          shouldAnimate = true;
          isActivePath = true;
        } else if (status === 'SUCCEEDED') {
          // For successful nodes, we check if this specific edge was part of the path
          const output = result?.output_data;
          const chosenBranch = output?._branch;

          const isBranchingNode = ['if_else', 'switch'].includes(sourceNode?.data.type || '');

          if (!isBranchingNode) {
            // Linear flow: success means path was taken
            shouldAnimate = true;
            isActivePath = true;
          } else if (chosenBranch !== undefined) {
            // Branching flow: only animate the edge that matches the chosen branch
            if (String(edge.sourceHandle) === String(chosenBranch)) {
              shouldAnimate = true;
              isActivePath = true;
            }
          }
        }

        return {
          ...edge,
          animated: shouldAnimate,
          data: { ...edge.data, isActivePath },
        } as any;
      })
    );
  }, [nodes, setEdges]);

  const alignNodes = useCallback(() => {
    // 1. Build adjacency list and find roots
    const adj: Record<string, string[]> = {};
    const inDegree: Record<string, number> = {};

    nodes.forEach(n => {
      adj[n.id] = [];
      inDegree[n.id] = 0;
    });

    edges.forEach(e => {
      if (adj[e.source]) adj[e.source].push(e.target);
      if (inDegree[e.target] !== undefined) inDegree[e.target]++;
    });

    const roots = nodes.filter(n => inDegree[n.id] === 0);
    if (roots.length === 0 && nodes.length > 0) roots.push(nodes[0]); // Fallback for cycles

    // 2. BFS to determine levels and vertical ordering
    const levels: Record<string, number> = {};
    const levelNodes: Record<number, string[]> = {};
    const queue: [string, number][] = roots.map(r => [r.id, 0]);
    const visited = new Set<string>();

    while (queue.length > 0) {
      const [id, level] = queue.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);

      levels[id] = Math.max(levels[id] || 0, level);
      if (!levelNodes[level]) levelNodes[level] = [];
      if (!levelNodes[level].includes(id)) levelNodes[level].push(id);

      (adj[id] || []).forEach(childId => {
        queue.push([childId, level + 1]);
      });
    }

    // 3. Calculate positions
    const HORIZONTAL_SPACING = 300;
    const VERTICAL_SPACING = 150;
    const newPositions: Record<string, XYPosition> = {};

    // First pass: Assign X based on levels
    nodes.forEach(node => {
      const level = levels[node.id] || 0;
      newPositions[node.id] = {
        x: level * HORIZONTAL_SPACING,
        y: 0
      };
    });

    // Second pass: Assign Y to achieve "straight lines" and structured branching
    const processedY = new Set<string>();

    const assignY = (nodeId: string, currentY: number) => {
      if (processedY.has(nodeId)) return;
      processedY.add(nodeId);

      newPositions[nodeId].y = currentY;
      const children = adj[nodeId] || [];

      if (children.length === 1) {
        // Straight line
        assignY(children[0], currentY);
      } else if (children.length > 1) {
        // Symmetrical branching
        const totalHeight = (children.length - 1) * VERTICAL_SPACING;
        let startY = currentY - totalHeight / 2;
        children.forEach(childId => {
          assignY(childId, startY);
          startY += VERTICAL_SPACING;
        });
      }
    };

    let rootY = 0;
    roots.forEach(r => {
      assignY(r.id, rootY);
      rootY += VERTICAL_SPACING * 2; // Space out different disconnected trees
    });

    // Carry over any nodes not reached by roots (extra safety)
    nodes.forEach(node => {
      if (!processedY.has(node.id)) {
        newPositions[node.id].y = 0;
      }
    });

    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        position: newPositions[node.id] || node.position,
      }))
    );

    // 5. Center and focus the workflow
    if (reactFlowInstance) {
      setTimeout(() => {
        reactFlowInstance.fitView({ duration: 800, padding: 0.2 });
      }, 50);
    }

    toast.success('Workflow perfectly aligned');
  }, [nodes, edges, setNodes]);

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
  }, [onExecutionUpdate, setNodes, stopPolling]);

  const beginExecutionTracking = useCallback((executionId: string) => {
    stopPolling();
    activeExecutionIdRef.current = executionId;
    onExecutionStart?.(executionId);
    setExecutionHistory((history) => [
      {
        executionId,
        status: 'PENDING',
        startedAt: null,
        finishedAt: null,
      },
      ...history,
    ]);
    void pollExecution(executionId);
    pollingIntervalRef.current = window.setInterval(() => {
      void pollExecution(executionId);
    }, 2000);
  }, [onExecutionStart, pollExecution, stopPolling]);

  const handleRunWorkflow = useCallback(async () => {
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
            setTriggerNode(trigger);
            setShowTriggerForm(true);
          } else if (trigger.data.type === 'webhook_trigger') {
            toast.success('Webhook trigger: Use HTTP POST to the webhook endpoint to trigger this workflow', { duration: 5000 });
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
        // Show form modal for form trigger
        setTriggerNode(trigger);
        setShowTriggerForm(true);
      } else if (trigger.data.type === 'webhook_trigger') {
        // For webhook triggers, show information about webhook usage
        toast.success('Webhook trigger: Use HTTP POST to the webhook endpoint to trigger this workflow', { duration: 5000 });
      } else {
        toast.error(`Unsupported trigger type: ${trigger.data.type}`);
      }
    } catch (error) {
      console.error('Execution failed:', error);
      toast.error('Workflow execution failed. Check console for details.');
    }
  }, [workflowId, nodes, edges, beginExecutionTracking]);

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
    connectingNode.current = null; // Clear connection state after successful connection
    toast.success('Nodes connected');
  }, [setEdges]);

  const onConnectStart = useCallback((_: any, { nodeId, handleId }: { nodeId: string | null; handleId?: string | null }) => {
    if (!nodeId) {
      connectingNode.current = null;
      return;
    }
    connectingNode.current = { nodeId, handleId: handleId ?? null };
  }, []);

  const onConnectEnd = useCallback(
    (event: any) => {
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
    [reactFlowInstance]
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
    [reactFlowInstance]
  );

  const addNodeAtPosition = useCallback((type: string, position: XYPosition) => {
    try {
      const newNode = createNode(type, position);
      const newNodeId = newNode.id;

      setNodes((nds) => nds.concat(newNode));
      toast.success(`${newNode.data.label} added`);

      if (connectingNode.current) {
        const sourceHandle = connectingNode.current.handleId ?? undefined;
        const newEdge: WorkflowEdge = {
          id: `e_${connectingNode.current!.nodeId}_${newNodeId}`,
          source: connectingNode.current!.nodeId,
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
        connectingNode.current = null;
      }

      setMenuVisible(false);
    } catch (error) {
      console.error(error);
    }
  }, [setNodes, setEdges]);

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: any) => {
    setSelectedNodeId(node.id);
  }, []);

  // Serialization logic for the backend
  const getWorkflowData = useCallback((name: string) => {
    return {
      name,
      definition: {
        nodes: nodes.map(n => ({
          id: n.id,
          type: n.data.type,
          label: n.data.label,
          position: n.position,
          config: n.data.config
        })),
        edges: edges.map((e: any) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
          branch: e.branch ?? e.sourceHandle ?? undefined,
        }))
      }
    };
  }, [nodes, edges]);

  // Deserialization logic (restore from backend format)
  const loadWorkflowData = useCallback((definition: any) => {
    if (!definition) return;

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
  }, [setNodes, setEdges]);

  // Expose serialization helpers
  useEffect(() => {
    (window as any).getCanvasWorkflowData = getWorkflowData;
    (window as any).loadCanvasWorkflowData = loadWorkflowData;
    return () => {
      delete (window as any).getCanvasWorkflowData;
      delete (window as any).loadCanvasWorkflowData;
    };
  }, [getWorkflowData, loadWorkflowData]);

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
  }, [setNodes]);

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

  const selectedNode = nodes.find(n => n.id === selectedNodeId);
  const upstreamData = selectedNodeId ? getUpstreamData(selectedNodeId) : null;

  return (
    <div className="flex-1 flex flex-col relative h-full bg-slate-50 dark:bg-slate-950 overflow-hidden">
      <div className="absolute left-1/2 top-5 z-20 -translate-x-1/2">
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 px-3 py-2 shadow-xl backdrop-blur-sm">
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
        <div className="flex-1 relative pt-16" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
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
            fitView
          >
            {/* Floating Action Buttons - Bottom Center */}
            <div
              className="absolute left-1/2 -translate-x-1/2 z-[1000] flex flex-row items-center gap-4 animate-in fade-in slide-in-from-bottom-6 duration-500"
              style={{ bottom: footerOffset + 24 }}
            >
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

                <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1 custom-scrollbar">
                  {Object.entries(NODE_LIBRARY).map(([category, nodes]) => (
                    <div key={category} className="mb-2 last:mb-0">
                      <div className="text-[10px] font-bold uppercase text-slate-300 dark:text-slate-600 mb-2 ml-1 tracking-widest">{category}</div>
                      <div className="grid grid-cols-1 gap-1">
                        {nodes.map(node => (
                          <button
                            key={node.type}
                            onClick={() => menuPosition && addNodeAtPosition(node.type, menuPosition)}
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
                  ))}
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
                onClose={() => setSelectedNodeId(null)}
                onUpdate={updateNodeConfig}
              />
            )}
          </ReactFlow>
        </div>
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
                    <div key={run.executionId} className="group relative rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 hover:bg-slate-50 dark:hover:bg-slate-800/50 p-5 transition-colors grid grid-cols-1 md:grid-cols-[1fr_auto] gap-4 items-center shadow-sm hover:shadow-md">
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
                        <span className={`inline-flex items-center rounded-full px-3 py-1.5 text-[10px] font-black tracking-widest uppercase shadow-sm ${run.status === 'SUCCEEDED' ? 'bg-emerald-100/80 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/20' : run.status === 'FAILED' ? 'bg-rose-100/80 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border border-rose-200/50 dark:border-rose-500/20' : run.status === 'RUNNING' ? 'bg-purple-100/80 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400 border border-purple-200/50 dark:border-purple-500/20' : 'bg-slate-100/80 text-slate-700 dark:bg-slate-500/20 dark:text-slate-400 border border-slate-200/50 dark:border-slate-500/20'}`}>
                          {run.status}
                        </span>
                        
                        {/* <button
                          type="button"
                          onClick={() => setActiveTab('editor')}
                          className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.1em] text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                        >
                          View
                          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                        </button> */}
                      </div>
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
