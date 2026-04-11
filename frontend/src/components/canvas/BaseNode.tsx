import React, { memo, useEffect } from 'react';
import { Handle, Position, NodeProps, useUpdateNodeInternals, useReactFlow } from 'reactflow';
import { Check, Loader2, AlertCircle, AlertTriangle } from 'lucide-react';
import { WorkflowNodeData } from '../../types/workflow';
import { CATEGORY_ACCENTS } from '../../constants/nodeLibrary';
import NodeBadge from '../sidebar/NodeBadge';

const hasIncompleteConfig = (type: string, config: Record<string, any>): boolean => {
  const requiredFields: Record<string, string[]> = {
    'if_else': ['field', 'operator', 'value'],
    'switch': ['field'],
    'filter': ['condition'],
  };
  
  const required = requiredFields[type];
  if (!required) return false;
  
  return required.some(field => !config[field]);
};

const BaseNode: React.FC<NodeProps<WorkflowNodeData>> = ({ id, data, selected }) => {
  const accentColor = CATEGORY_ACCENTS[data.category] || '#cbd5e1';
  const updateNodeInternals = useUpdateNodeInternals();
  const { deleteElements } = useReactFlow();
  const hasIncomplete = hasIncompleteConfig(data.type, data.config);

  // Debug log whenever data changes
  useEffect(() => {
    if (data.status) {
      console.log(`BaseNode ${id} status changed to:`, data.status);
    }
  }, [data.status, id]);

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
      className={`px-3 py-2.5 rounded-xl border-2 transition-all shadow-none min-w-[150px] max-w-[150px] bg-white dark:bg-slate-900 group/node relative 
        ${selected ? 'ring-2 ring-blue-500/10 border-blue-500' : 'border-slate-200 dark:border-slate-800'}
        ${data.status === 'RUNNING' ? 'border-emerald-600 ring-4 ring-emerald-400/30 bg-emerald-50 dark:bg-emerald-900/20 animate-pulse' : ''}
        ${data.status === 'SUCCEEDED' ? 'border-emerald-500 ring-4 ring-emerald-500/10 dark:bg-emerald-900/10' : ''}
        ${data.status === 'FAILED' ? 'border-rose-500 ring-4 ring-rose-500/10 dark:bg-rose-900/10' : ''}
      `}
      style={{ borderTop: `px solid ${data.status === 'RUNNING' ? '#045e41' : accentColor}` }}
      title={hasIncomplete ? 'This node is missing required configuration' : ''}
    >
      {/* Execution Status Icon */}
      {data.status && (
        <div className="absolute -top-3 -right-3 p-1 rounded-full bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 shadow-md z-20">
          {data.status === 'RUNNING' && <Loader2 size={12} className="text-emerald-600 dark:text-emerald-400 animate-spin" />}
          {data.status === 'SUCCEEDED' && <Check size={12} className="text-emerald-500 dark:text-emerald-400" strokeWidth={3} />}
          {data.status === 'FAILED' && <AlertCircle size={12} className="text-rose-500 dark:text-rose-400" />}
        </div>
      )}

      {/* Config Incomplete Warning */}
      {hasIncomplete && !data.status && (
        <div className="absolute -top-3 -left-3 p-1 rounded-full bg-amber-100 dark:bg-amber-900 border border-amber-300 dark:border-amber-700 shadow-md z-20" title="Missing configuration">
          <AlertTriangle size={12} className="text-amber-600 dark:text-amber-400" />
        </div>
      )}

      {/* Node Delete Button */}
      <button
        id={`delete-node-${id}`}
        onClick={handleDeleteNode}
        title="Remove node"
        className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-900 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all flex items-center justify-center shadow-sm z-30 opacity-0 group-hover/node:opacity-100 nodrag"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      </button>

      <Handle
        type="target"
        position={Position.Left}
        className={`!w-1.5 !h-1.5 border border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-slate-200 dark:!bg-slate-700'}`}
        style={{ left: -4 }}
      />

      <div className="flex flex-col gap-1 mt-0.5">
        <div className="flex items-center justify-between gap-3">
          <span className={`text-[8px] font-black uppercase tracking-widest`} style={{ color: data.status === 'RUNNING' ? '#059669' : accentColor }}>
            {data.category}
          </span>
          {data.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>

        <h3 className={`text-xs font-bold leading-tight truncate ${data.status === 'RUNNING' ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-800 dark:text-slate-100'}`}>{data.label}</h3>

        <div className={`mt-1.5 flex items-center justify-between border-t ${data.status === 'RUNNING' ? 'border-emerald-200 dark:border-emerald-900/50' : 'border-slate-50 dark:border-slate-800/50'} pt-1.5 text-[8px] font-bold uppercase tracking-tighter ${data.status === 'RUNNING' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500'}`}>
          <span className="truncate max-w-[100px]">{data.type.replace('_', ' ')}</span>
          <div className={`w-1 h-1 rounded-full ${data.status === 'RUNNING' ? 'bg-emerald-500 animate-pulse' : data.is_dummy ? 'bg-slate-200 dark:bg-slate-700' : 'bg-green-400'}`} />
        </div>
      </div>

      {/* Dynamic Source Handles for Branching */}
      {data.type === 'if_else' ? (
        <>
          <div className="absolute -right-1 top-[25%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">True</span>
            <Handle type="source" position={Position.Right} id="true" className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-emerald-500 transition-all pointer-events-auto ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-emerald-400'}`} />
          </div>
          <div className="absolute -right-1 top-[75%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">False</span>
            <Handle type="source" position={Position.Right} id="false" className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-rose-500 transition-all pointer-events-auto ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-rose-400'}`} />
          </div>
        </>
      ) : data.type === 'switch' ? (
        <div className="absolute -right-1 top-0 bottom-0 flex flex-col justify-center gap-4 py-2 pointer-events-none">
          {(data.config.cases || []).map((c: any, i: number) => (
            <div key={c.id || i} className="flex items-center justify-end w-32 translate-x-1">
              <span className="text-[6px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 max-w-[50px] truncate pointer-events-auto" title={c.label}>
                {c.label || `Case ${i + 1}`}
              </span>
              <Handle type="source" position={Position.Right} id={c.id || c.label || `case_${i}`} className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all pointer-events-auto ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-blue-400'}`} />
            </div>
          ))}
          <div className="flex items-center justify-end w-32 translate-x-1">
            <span className="text-[6px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">Default</span>
            <Handle type="source" position={Position.Right} id="default" className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-slate-500 transition-all pointer-events-auto ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-slate-400'}`} />
          </div>
        </div>
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${data.status === 'RUNNING' ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
          style={{ right: -4 }}
        />
      )}
    </div>
  );
};

export default memo(BaseNode);

