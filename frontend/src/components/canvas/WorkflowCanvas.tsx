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
import { NODE_LIBRARY } from '../../constants/nodeLibrary';
import { createNode } from '../../utils/nodeFactory';
import ConfigPanel from '../config/ConfigPanel';

const nodeTypes = {
  trigger: BaseNode,
  action: BaseNode,
  transform: BaseNode,
  ai: BaseNode,
};

const initialNodes: WorkflowNode[] = [];
const initialEdges: WorkflowEdge[] = [];

const WorkflowCanvas: React.FC = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const connectingNodeId = useRef<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<any>(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);

  // Quick Add State
  const [menuVisible, setMenuVisible] = useState(false);
  const [menuPosition, setMenuPosition] = useState<XYPosition | null>(null);

  // Config Panel State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const onConnect = useCallback((params: Connection) => {
    if (!params.source || !params.target) return;

    const newEdge: WorkflowEdge = {
      ...params,
      source: params.source,
      target: params.target,
      id: `e_${params.source}_${params.target}_${params.sourceHandle || 'def'}_${Date.now()}`,
      animated: true,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      branch: params.sourceHandle || undefined
    };
    setEdges((eds) => addEdge(newEdge as any, eds));
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

      if (connectingNodeId.current) {
        setEdges((eds) => addEdge({
          id: `e_${connectingNodeId.current}_${newNodeId}`,
          source: connectingNodeId.current!,
          target: newNodeId,
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
          ...(e.branch ? { branch: e.branch } : {})
        }))
      }
    };
  }, [nodes, edges]);

  // Deserialization logic (restore from backend format)
  const loadWorkflowData = useCallback((definition: any) => {
    if (!definition) return;
    
    // Map simplified nodes back to React Flow format
    const rfNodes: WorkflowNode[] = (definition.nodes || []).map((n: any) => {
      // Determine the category based on the node library structure
      const category = NODE_LIBRARY.trigger.some(ref => ref.type === n.type) ? 'trigger' :
                      NODE_LIBRARY.action.some(ref => ref.type === n.type) ? 'action' :
                      NODE_LIBRARY.transform.some(ref => ref.type === n.type) ? 'transform' : 'ai';
      
      return {
        id: n.id,
        type: category, // Map category back to React Flow's 'type' for correct component rendering
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
    setEdges(definition.edges || []);
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

    // Merge outputs from all direct parents
    const combinedData: Record<string, any> = {};
    upstreamEdges.forEach(edge => {
      const sourceNode = nodes.find(n => n.id === edge.source);
      if (sourceNode?.data.last_output) {
        Object.assign(combinedData, sourceNode.data.last_output);
      } else {
        // Provide rich mock data based on node type if no output yet
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
    <div className="flex-1 relative h-full bg-slate-50 overflow-hidden" ref={reactFlowWrapper}>
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
        nodeTypes={nodeTypes}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#000000ff" />
        <Controls position="bottom-right" className="bg-white border border-slate-200 rounded-xl shadow-lg !m-4 !mr-[230px]" />
        <MiniMap
          className="bg-white border border-slate-200 rounded-xl shadow-lg !m-4 overflow-hidden"
          nodeColor={(n) => {
            const data = n.data as WorkflowNodeData;
            if (data.category === 'trigger') return '#10b981';
            if (data.category === 'action') return '#3b82f6';
            if (data.category === 'transform') return '#f59e0b';
            if (data.category === 'ai') return '#a855f7';
            return '#cbd5e1';
          }}
          maskColor="rgba(241, 245, 249, 0.7)"
          pannable
          zoomable
        />



        {menuVisible && menuPosition && (
          <div
            className="absolute z-[1000] bg-white border border-slate-200 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] p-4 w-72 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200 pointer-events-auto"
            style={{
              left: reactFlowInstance ? reactFlowInstance.flowToScreenPosition(menuPosition).x - (reactFlowWrapper.current?.getBoundingClientRect().left || 0) : 0,
              top: reactFlowInstance ? reactFlowInstance.flowToScreenPosition(menuPosition).y - (reactFlowWrapper.current?.getBoundingClientRect().top || 0) : 0,
              transform: 'translate(-50%, -50%)'
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-50 pb-2">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Quick Add Node</h3>
              </div>
              <button
                onClick={() => setMenuVisible(false)}
                className="p-1 hover:bg-slate-100 rounded-md transition-colors text-slate-400 hover:text-slate-600"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
              </button>
            </div>

            <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1 custom-scrollbar">
              {Object.entries(NODE_LIBRARY).map(([category, nodes]) => (
                <div key={category} className="mb-2 last:mb-0">
                  <div className="text-[10px] font-bold uppercase text-slate-300 mb-2 ml-1 tracking-widest">{category}</div>
                  <div className="grid grid-cols-1 gap-1">
                    {nodes.map(node => (
                      <button
                        key={node.type}
                        onClick={() => addNodeAtPosition(node.type, menuPosition)}
                        className="flex flex-col gap-0.5 p-2.5 rounded-xl hover:bg-slate-50 border border-transparent hover:border-slate-100 transition-all text-left group"
                      >
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ring-4 ring-white shadow-sm ${category === 'trigger' ? 'bg-emerald-400' :
                            category === 'action' ? 'bg-blue-400' :
                              category === 'transform' ? 'bg-amber-400' : 'bg-purple-400'
                            }`} />
                          <span className="text-sm font-bold text-slate-700 group-hover:text-blue-600">{node.label}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 ml-4 line-clamp-1">{node.description}</span>
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
            node={selectedNode}
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
