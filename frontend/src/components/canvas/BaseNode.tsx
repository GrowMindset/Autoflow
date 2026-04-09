import React, { memo, useEffect } from 'react';
import { Handle, Position, NodeProps, useUpdateNodeInternals, useReactFlow } from 'reactflow';
import { WorkflowNodeData } from '../../types/workflow';
import { CATEGORY_ACCENTS } from '../../constants/nodeLibrary';
import NodeBadge from '../sidebar/NodeBadge';

const BaseNode: React.FC<NodeProps<WorkflowNodeData>> = ({ id, data, selected }) => {
  const accentColor = CATEGORY_ACCENTS[data.category] || '#cbd5e1';
  const updateNodeInternals = useUpdateNodeInternals();
  const { deleteElements } = useReactFlow();

  const handleDeleteNode = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ nodes: [{ id }] });
  };

  // Notify React Flow when handles change (e.g. for Switch node cases)
  const caseIds = (data.config.cases || []).map((c: any) => c.id).join(',');
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, caseIds, updateNodeInternals]);

  return (
    <div
      className={`px-3 py-2.5 rounded-xl border border-slate-200 transition-all shadow-sm min-w-[150px] max-w-[150px] bg-white group/node ${selected ? 'ring-2 ring-blue-500/10 border-blue-500' : ''}`}
      style={{ borderTop: `4px solid ${accentColor}` }}
    >
      {/* Node Delete Button */}
      <button
        id={`delete-node-${id}`}
        onClick={handleDeleteNode}
        title="Remove node"
        className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-white border border-slate-200 text-slate-300 hover:text-red-500 hover:border-red-300 hover:bg-red-50 transition-all flex items-center justify-center shadow-sm z-10 opacity-0 group-hover/node:opacity-100 nodrag"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      </button>

      <Handle
        type="target"
        position={Position.Left}
        className="!w-1.5 !h-1.5 !bg-slate-200 border border-white hover:!bg-blue-500 transition-colors"
        style={{ left: -4 }}
      />

      <div className="flex flex-col gap-1 mt-0.5">
        <div className="flex items-center justify-between gap-3">
          <span className={`text-[8px] font-black uppercase tracking-widest`} style={{ color: accentColor }}>
            {data.category}
          </span>
          {data.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>

        <h3 className="text-xs font-bold text-slate-800 leading-tight truncate">{data.label}</h3>

        <div className="mt-1.5 flex items-center justify-between border-t border-slate-50 pt-1.5 text-[8px] font-bold text-slate-400 uppercase tracking-tighter">
          <span className="truncate max-w-[100px]">{data.type.replace('_', ' ')}</span>
          <div className={`w-1 h-1 rounded-full ${data.is_dummy ? 'bg-slate-200' : 'bg-green-400'}`} />
        </div>
      </div>

      {/* Dynamic Source Handles for Branching */}
      {data.type === 'if_else' ? (
        <>
          <div className="absolute -right-1 top-[25%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 bg-white px-1 py-0.5 rounded border border-slate-100 shadow-sm mr-2 pointer-events-auto">True</span>
            <Handle type="source" position={Position.Right} id="true" className="!w-2 !h-2 !bg-emerald-400 border-2 border-white hover:!bg-emerald-500 transition-all pointer-events-auto" />
          </div>
          <div className="absolute -right-1 top-[75%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 bg-white px-1 py-0.5 rounded border border-slate-100 shadow-sm mr-2 pointer-events-auto">False</span>
            <Handle type="source" position={Position.Right} id="false" className="!w-2 !h-2 !bg-rose-400 border-2 border-white hover:!bg-rose-500 transition-all pointer-events-auto" />
          </div>
        </>
      ) : data.type === 'switch' ? (
        <div className="absolute -right-1 top-0 bottom-0 flex flex-col justify-center gap-4 py-2 pointer-events-none">
          {(data.config.cases || []).map((c: any, i: number) => (
            <div key={c.id || i} className="flex items-center justify-end w-32 translate-x-1">
              <span className="text-[6px] font-black uppercase text-slate-400 bg-white px-1 py-0.5 rounded border border-slate-100 shadow-sm mr-2 max-w-[50px] truncate pointer-events-auto" title={c.label}>
                {c.label || `Case ${i + 1}`}
              </span>
              <Handle type="source" position={Position.Right} id={c.id || c.label || `case_${i}`} className="!w-2 !h-2 !bg-blue-400 border-2 border-white hover:!bg-blue-500 transition-all pointer-events-auto" />
            </div>
          ))}
          <div className="flex items-center justify-end w-32 translate-x-1">
            <span className="text-[6px] font-black uppercase text-slate-400 bg-white px-1 py-0.5 rounded border border-slate-100 shadow-sm mr-2 pointer-events-auto">Default</span>
            <Handle type="source" position={Position.Right} id="default" className="!w-2 !h-2 !bg-slate-400 border-2 border-white hover:!bg-slate-500 transition-all pointer-events-auto" />
          </div>
        </div>
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2 !h-2 !bg-slate-300 border-2 border-white hover:!bg-blue-500 transition-all"
          style={{ right: -4 }}
        />
      )}
    </div>
  );
};

export default memo(BaseNode);

