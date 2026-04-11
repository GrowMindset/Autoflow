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
import { executionService } from '../../services/executionService';
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

interface WorkflowCanvasProps {
  workflowId: string;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({ workflowId }) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const connectingNodeId = useRef<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<any>(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);
  const { isDark } = useTheme();

  // Quick Add State
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState<XYPosition | null>(null);

  // Config Panel State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Alignment Detection
  const [isAligned, setIsAligned] = useState(true);

  useEffect(() => {
    const misaligned = nodes.some(
      (node) => node.position.x % 20 !== 0 || node.position.y % 20 !== 0
    );
    setIsAligned(!misaligned);
  }, [nodes]);

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

    // 4. Update nodes
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        position: newPositions[node.id] || node.position,
      }))
    );
    toast.success('Workflow perfectly aligned');
  }, [nodes, edges, setNodes]);

  const handleRunWorkflow = useCallback(async () => {
    if (workflowId === 'new') {
      toast.error('Please save your workflow before running');
      return;
    }

    try {
      await toast.promise(
        executionService.runWorkflow(workflowId),
        {
          loading: 'Starting execution...',
          success: 'Workflow execution started!',
          error: 'Failed to start execution',
        }
      );
    } catch (error) {
      console.error('Execution failed:', error);
    }
  }, [workflowId]);

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
      id: `e_${params.source}_${params.target}_${params.sourceHandle || 'def'}_${Date.now()}`,
      type: 'deletable',
      animated: true,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' }
    };
    setEdges((eds) => addEdge(newEdge as any, eds));
    toast.success('Nodes connected');
  }, [setEdges]);

  const onConnectStart = useCallback((_: any, { nodeId }: { nodeId: string | null }) => {
    connectingNodeId.current = nodeId;
  }, []);

  const onConnectEnd = useCallback(
    (event: any) => {
      if (!connectingNodeId.current || !reactFlowInstance) return;

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

      if (connectingNodeId.current) {
        setEdges((eds) => addEdge({
          id: `e_${connectingNodeId.current}_${newNodeId}`,
          source: connectingNodeId.current!,
          target: newNodeId,
          type: 'deletable',
          animated: true,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#94a3b8',
          },
        }, eds));
        connectingNodeId.current = null;
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
          targetHandle: e.targetHandle
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
      animated: true,
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
    <div className="flex-1 relative h-full bg-slate-50 dark:bg-slate-950 overflow-hidden" ref={reactFlowWrapper}>
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
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-[1000] flex flex-row items-center gap-4 animate-in fade-in slide-in-from-bottom-6 duration-500">
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
        <Controls position="bottom-right" className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg !m-4 !mr-[230px]" />
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
  );
};

export default WorkflowCanvas;
