import React, { memo, useEffect, useMemo, useState } from 'react';
import { Handle, Position, NodeProps, useUpdateNodeInternals, useReactFlow, useEdges } from 'reactflow';
import { Check, Loader2, AlertCircle, AlertTriangle, Plus } from 'lucide-react';
import { WorkflowNodeData } from '../../types/workflow';
import { CATEGORY_ACCENTS } from '../../constants/nodeLibrary';
import NodeBadge from '../sidebar/NodeBadge';
import { getNodeCountdownLabel, shouldShowLiveNodeCountdown } from '../../utils/nodeTimers';

const SHEETS_OPERATION_ALIASES: Record<string, string> = {
  append: 'append_row',
  append_rows: 'append_row',
  add_row: 'append_row',
  add_rows: 'append_row',
  delete: 'delete_rows',
  delete_row: 'delete_rows',
  remove_row: 'delete_rows',
  remove_rows: 'delete_rows',
  overwrite: 'overwrite_row',
  override: 'overwrite_row',
  update: 'overwrite_row',
  upsert: 'upsert_row',
  add_column: 'add_columns',
  create_columns: 'add_columns',
  delete_column: 'delete_columns',
  remove_column: 'delete_columns',
  remove_columns: 'delete_columns',
};

const normalizeSheetsOperation = (rawOperation: any, upsertIfMissing: boolean): string => {
  const token = String(rawOperation || '').trim().toLowerCase();
  if (!token) {
    return upsertIfMissing ? 'upsert_row' : 'overwrite_row';
  }
  return SHEETS_OPERATION_ALIASES[token] || token;
};

const getMissingRequirements = (type: string, config: Record<string, any>, isChatModelConnected: boolean): string[] => {
  const missing: string[] = [];

  const requiredFields: Record<string, string[]> = {
    'if_else': ['field', 'operator'],
    'switch': ['field'],
    'filter': ['input_key', 'field', 'operator', 'value'],
    'get_gmail_message': ['credential_id'],
    'send_gmail_message': ['credential_id', 'to', 'subject', 'body'],
    'create_google_sheets': ['credential_id', 'title'],
    'delay': ['amount', 'unit'],
    'file_read': ['file_path'],
    'file_write': ['file_path'],
    'create_google_docs': ['credential_id', 'title'],
    'update_google_docs': ['credential_id', 'document_id', 'operation', 'text'],
    'telegram': ['credential_id', 'message'],
    'whatsapp': ['credential_id', 'to_number', 'template_name'],
    'ai_agent': ['command'],
    'chat_model_openai': ['credential_id', 'model'],
    'chat_model_groq': ['credential_id', 'model'],
  };

  const fields = requiredFields[type] || [];
  for (const field of fields) {
    if (!config[field]) {
      missing.push(`Required field '${field}' is missing`);
    }
  }

  if (type === 'if_else') {
    const valueMode = String(config.value_mode || 'literal').toLowerCase() === 'field'
      ? 'field'
      : 'literal';
    if (valueMode === 'field') {
      if (!String(config.value_field || '').trim()) {
        missing.push("Required field 'value_field' is missing for value_mode='field'");
      }
    } else {
      const value = config.value;
      const hasLiteral = value !== undefined && value !== null && String(value).trim() !== '';
      if (!hasLiteral) {
        missing.push("Required field 'value' is missing for value_mode='literal'");
      }
    }
  }

  if (type === 'update_google_docs' && config.operation === 'replace_all_text' && !config.match_text) {
    missing.push("Required field 'match_text' is missing for replace_all_text operation");
  }

  if (type === 'search_update_google_sheets') {
    const sourceType = String(config.spreadsheet_source_type || 'id').trim().toLowerCase();
    const operation = normalizeSheetsOperation(config.operation, Boolean(config.upsert_if_not_found));

    if (sourceType === 'url') {
      if (!String(config.spreadsheet_url || '').trim()) {
        missing.push("Required field 'spreadsheet_url' is missing for spreadsheet_source_type='url'");
      }
    } else if (!String(config.spreadsheet_id || '').trim()) {
      missing.push("Required field 'spreadsheet_id' is missing");
    }

    if (!String(config.sheet_name || '').trim()) {
      missing.push("Required field 'sheet_name' is missing");
    }

    const hasLegacyUpdate =
      String(config.update_column || '').trim() !== '' &&
      Object.prototype.hasOwnProperty.call(config, 'update_value');
    const hasMappings = Array.isArray(config.update_mappings)
      && config.update_mappings.some((item: any) => String(item?.column || '').trim() !== '');

    const appendColumns = Array.isArray(config.append_columns) ? config.append_columns : [];
    const appendValues = Array.isArray(config.append_values) ? config.append_values : [];
    const appendColumnsClean = appendColumns.filter((value: any) => String(value || '').trim() !== '');
    const columnsToAdd = Array.isArray(config.columns_to_add)
      ? config.columns_to_add.filter((value: any) => String(value || '').trim() !== '')
      : [];
    const columnsToDelete = Array.isArray(config.columns_to_delete)
      ? config.columns_to_delete.filter((value: any) => String(value || '').trim() !== '')
      : [];

    if (operation === 'append_row') {
      if (appendColumnsClean.length === 0 && !hasMappings) {
        missing.push("Provide 'update_mappings' (or legacy append_columns/append_values) for append_row.");
      }
      if (!hasMappings && appendColumnsClean.length > 0 && appendValues.length !== appendColumns.length) {
        missing.push("'append_columns' and 'append_values' must have the same length.");
      }
    } else if (operation === 'delete_rows') {
      if (!String(config.key_column || config.search_column || '').trim()) {
        missing.push("Required field 'key_column' is missing for delete_rows.");
      }
      if (!String(config.key_value || config.search_value || '').trim()) {
        missing.push("Required field 'key_value' is missing for delete_rows.");
      }
    } else if (operation === 'overwrite_row' || operation === 'upsert_row') {
      if (!String(config.key_column || config.search_column || '').trim()) {
        missing.push("Required field 'key_column' is missing.");
      }
      if (!String(config.key_value || config.search_value || '').trim()) {
        missing.push("Required field 'key_value' is missing.");
      }
      if (!hasMappings && appendColumnsClean.length === 0 && !hasLegacyUpdate) {
        missing.push("Provide 'update_mappings' (or append columns/values) for row update.");
      }
    } else if (operation === 'add_columns') {
      if (columnsToAdd.length === 0) {
        missing.push("Required field 'columns_to_add' is missing.");
      }
    } else if (operation === 'delete_columns') {
      if (columnsToDelete.length === 0) {
        missing.push("Required field 'columns_to_delete' is missing.");
      }
    } else if (!operation) {
      if (!hasLegacyUpdate && !hasMappings) {
        missing.push("Required field 'update_mappings' (or legacy update_column/update_value) is missing");
      }
    }
  }

  if (type === 'delay') {
    const hasUntil = String(config.until_datetime || '').trim() !== '';
    const hasAmount = String(config.amount || '').trim() !== '';
    if (!hasUntil && !hasAmount) {
      missing.push("Required field 'amount' (or 'until_datetime') is missing");
    }
  }

  if (type === 'ai_agent' && !isChatModelConnected) {
    missing.push('Requires a Chat Model node connected to its bottom handle');
  }

  return missing;
};

const BaseNode: React.FC<NodeProps<WorkflowNodeData>> = ({ id, data, selected }) => {
  const accentColor = CATEGORY_ACCENTS[data.category] || '#cbd5e1';
  const updateNodeInternals = useUpdateNodeInternals();
  const { deleteElements } = useReactFlow();
  const edges = useEdges();

  const isChatModelConnected = edges.some(
    (e) => e.target === id && e.targetHandle === 'chat_model'
  );

  const missingReqs = getMissingRequirements(data.type, data.config, isChatModelConnected);
  const hasIncomplete = missingReqs.length > 0;
  const aiNodeErrorMessage = data.type === 'ai_agent' && data.status === 'FAILED'
    ? (data.last_execution_result?.error_message || '')
    : '';
  const aiNodeErrorPreview = aiNodeErrorMessage.length > 90
    ? `${aiNodeErrorMessage.slice(0, 90)}...`
    : aiNodeErrorMessage;
  const isScheduleLive = data.type === 'schedule_trigger' && Boolean(data.schedule_is_active);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const shouldShowLiveCountdown = shouldShowLiveNodeCountdown(data);
  const countdownLabel = useMemo(
    () => getNodeCountdownLabel(data, nowMs),
    [data, nowMs],
  );
  const normalizedStatus = String(data.status || '').toUpperCase();
  const isWaitingLike = normalizedStatus === 'WAITING' || normalizedStatus === 'QUEUED';
  const isExecutionVisualActive = data.workflow_execution_visual_active !== false;
  const isRunningLike = (normalizedStatus === 'RUNNING' || isWaitingLike) && isExecutionVisualActive;
  const isSucceeded = normalizedStatus === 'SUCCEEDED';
  const isFailed = normalizedStatus === 'FAILED';

  useEffect(() => {
    if (!shouldShowLiveCountdown || !isExecutionVisualActive) return;
    setNowMs(Date.now());
    const timer = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [isExecutionVisualActive, shouldShowLiveCountdown]);

  const handleDeleteNode = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ nodes: [{ id }] });
  };

  // Notify React Flow when handles change (e.g. for Switch node cases)
  const caseIds = (data.config.cases || [])
    .map((c: any) => String(c?.id || c?.label || ''))
    .join(',');
  const defaultCaseHandle = String(data.config.default_case || 'default');
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, caseIds, defaultCaseHandle, updateNodeInternals]);
  
  const normalizeHandle = (handleId: string | null | undefined) => handleId ?? null;

  const isHandleConnected = (handleId: string | null, connectionType: 'source' | 'target' = 'source') => {
    const normalizedHandle = normalizeHandle(handleId);

    if (connectionType === 'target') {
      return edges.some(
        (edge) => edge.target === id && normalizeHandle(edge.targetHandle) === normalizedHandle
      );
    }

    return edges.some(
      (edge) => edge.source === id && normalizeHandle(edge.sourceHandle) === normalizedHandle
    );
  };

  const handlePlusClick = (
    e: React.MouseEvent,
    handleId: string | null,
    connectionType: 'source' | 'target' = 'source'
  ) => {
    e.stopPropagation();
    
    // Trigger the quick add menu in WorkflowCanvas via a custom event
    const event = new CustomEvent('rf-quick-add', {
        detail: {
            nodeId: id,
            handleId: handleId,
            connectionType,
            clientX: e.clientX,
            clientY: e.clientY,
        }
    });
    window.dispatchEvent(event);
  };

  const PlusButton = ({
    handleId,
    className = "",
    connectionType = 'source',
  }: {
    handleId: string | null;
    className?: string;
    connectionType?: 'source' | 'target';
  }) => {
    // Keep "+" visible on source handles so users can fan-out to multiple nodes.
    // For target handles, keep the previous behavior (hide once connected).
    if (connectionType === 'target' && isHandleConnected(handleId, connectionType)) return null;
    
    return (
      <button
        onClick={(e) => handlePlusClick(e, handleId, connectionType)}
        className={`nodrag pointer-events-auto absolute z-[100] w-4 h-4 bg-slate-800 dark:bg-slate-800 text-slate-400 border border-slate-700 rounded-md flex items-center justify-center shadow-lg hover:bg-slate-700 hover:text-white active:scale-95 transition-all ${className}`}
        title="Add node here"
      >
        <Plus size={10} strokeWidth={4} />
      </button>
    );
  };

  return (
    <div
      className={`px-3 py-2.5 rounded-xl border-2 transition-colors duration-200 shadow-none min-w-[150px] max-w-[150px] group/node relative 
        ${selected ? 'ring-2 ring-blue-500/10 border-blue-500' : 'border-slate-200 dark:border-slate-800'}
        ${isScheduleLive ? 'shadow-[0_0_20px_rgba(6,182,212,0.18)]' : ''}
        ${isRunningLike ? 'border-emerald-600 ring-[6px] ring-emerald-500/20 bg-emerald-50/30 dark:bg-emerald-900/10 animate-pulse' : ''}
        ${isSucceeded ? 'bg-emerald-50/30 dark:bg-emerald-500/5 border-emerald-500 shadow-[0_0_25px_rgba(16,185,129,0.2)] ring-[6px] ring-emerald-500/30' : 'bg-white dark:bg-slate-900'}
        ${isFailed ? 'bg-rose-50/30 dark:bg-rose-500/5 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.2)] ring-[6px] ring-rose-500/30' : ''}
      `}
      style={{
        borderTop: `6px solid ${isRunningLike || isSucceeded ? '#10b981' :
            isFailed ? '#f43f5e' :
              isScheduleLive ? '#06b6d4' :
              accentColor
          }`
      }}
      title={hasIncomplete ? 'This node is missing required configuration' : ''}
    >
      {isScheduleLive && (
        <>
          <div className="pointer-events-none absolute -inset-[6px] rounded-2xl border border-cyan-400/40 animate-pulse" />
          <div className="pointer-events-none absolute -bottom-2 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-full border border-cyan-300/70 bg-cyan-50/95 px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wide text-cyan-700 shadow-sm dark:border-cyan-700/70 dark:bg-cyan-950/90 dark:text-cyan-300">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan-500 animate-pulse" />
            live
          </div>
        </>
      )}

      {isExecutionVisualActive && countdownLabel && (
        <div className="absolute -top-8 left-1/2 -translate-x-1/2 z-20 px-2 py-1 rounded-md bg-slate-900 text-white text-[9px] font-black tracking-wide border border-slate-700 shadow-lg whitespace-nowrap">
          {countdownLabel}
        </div>
      )}

      {/* Execution Status Icon */}
      {data.status && (
        <div className={`absolute -top-3 -right-3 p-1 rounded-full border shadow-md z-20 transition-all duration-300 ${isSucceeded ? 'bg-emerald-500 border-emerald-400' :
            isFailed ? 'bg-rose-500 border-rose-400' :
              'bg-white dark:bg-slate-800 border-slate-100 dark:border-slate-700'
          }`}>
          {isRunningLike && <Loader2 size={12} className="text-emerald-600 dark:text-emerald-400 animate-spin" />}
          {isSucceeded && <Check size={12} className="text-white" strokeWidth={4} />}
          {isFailed && <AlertCircle size={12} className="text-white" />}
        </div>
      )}
      {!data.status && isScheduleLive && (
        <div className="absolute -top-3 -right-3 p-1 rounded-full border shadow-md z-20 transition-all duration-300 bg-cyan-50 border-cyan-300 dark:bg-cyan-950/90 dark:border-cyan-700">
          <Loader2 size={12} className="text-cyan-600 dark:text-cyan-400 animate-spin" />
        </div>
      )}

      {/* Config Incomplete Warning */}
      {hasIncomplete && !data.status && (
        <div
          className="absolute -top-3 -left-3 p-1 rounded-full bg-amber-100 dark:bg-amber-900 border border-amber-300 dark:border-amber-700 shadow-md z-20 cursor-help"
          title={`INCOMPLETE CONFIGURATION:\n• ${missingReqs.join('\n• ')}`}
        >
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
        className={`!w-1.5 !h-1.5 border border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike || isSucceeded ? '!bg-emerald-500' :
            isFailed ? '!bg-rose-500' :
              '!bg-slate-200 dark:!bg-slate-700'
          }`}
        style={{ left: -4 }}
      />

      <div className="flex flex-col gap-1 mt-0.5">
        <div className="flex items-center justify-between gap-3">
          <span className={`text-[8px] font-black uppercase tracking-widest`} style={{
            color: isRunningLike || isSucceeded ? '#059669' :
              isFailed ? '#e11d48' :
                accentColor
          }}>
            {data.category}
          </span>
          {data.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>

        <h3 className={`text-xs font-bold leading-tight truncate ${isRunningLike || isSucceeded ? 'text-emerald-900 dark:text-emerald-100' :
            isFailed ? 'text-rose-900 dark:text-rose-100' :
              'text-slate-800 dark:text-slate-100'
          }`}>{data.label}</h3>

        {aiNodeErrorPreview && (
          <div
            title={aiNodeErrorMessage}
            className="rounded-md border border-rose-200 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-900/20 px-1.5 py-1 text-[7px] text-rose-600 dark:text-rose-300 leading-tight line-clamp-2"
          >
            {aiNodeErrorPreview}
          </div>
        )}

        <div className={`mt-1.5 flex items-center justify-between border-t ${isRunningLike || isSucceeded ? 'border-emerald-200 dark:border-emerald-900/50' :
            isFailed ? 'border-rose-200 dark:border-rose-900/50' :
              'border-slate-50 dark:border-slate-800/50'
          } pt-1.5 text-[8px] font-bold uppercase tracking-tighter ${isRunningLike || isSucceeded ? 'text-emerald-600 dark:text-emerald-400' :
            isFailed ? 'text-rose-600 dark:text-rose-400' :
              'text-slate-400 dark:text-slate-500'
          }`}>
          <span className="truncate max-w-[100px]">{data.type.replace('_', ' ')}</span>
          <div className={`w-1 h-1 rounded-full ${isRunningLike ? 'bg-emerald-500 animate-pulse' :
              isSucceeded ? 'bg-emerald-500' :
                isFailed ? 'bg-rose-500' :
                  isScheduleLive ? 'bg-cyan-500 animate-pulse' :
                  data.is_dummy ? 'bg-slate-200 dark:bg-slate-700' : 'bg-green-400'
            }`} />
        </div>
      </div>

      {/* Dynamic Source Handles for Branching */}
      {data.type === 'if_else' ? (
        <>
          <div className="absolute -right-1 top-[25%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">True</span>
            <Handle type="source" position={Position.Right} id="true" className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-emerald-500 transition-all pointer-events-auto ${isRunningLike ? '!bg-emerald-500' : '!bg-emerald-400'}`} />
            <PlusButton handleId="true" className="-right-10" />
          </div>
          <div className="absolute -right-1 top-[75%] flex items-center justify-end w-20 pointer-events-none">
            <span className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">False</span>
            <Handle type="source" position={Position.Right} id="false" className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-rose-500 transition-all pointer-events-auto ${isRunningLike ? '!bg-emerald-500' : '!bg-rose-400'}`} />
            <PlusButton handleId="false" className="-right-10" />
          </div>
        </>
      ) : data.type === 'switch' ? (
        <div className="absolute -right-1 top-0 bottom-0 flex flex-col justify-center gap-4 py-2 pointer-events-none">
          {(data.config.cases || []).map((c: any, i: number) => {
            const caseId = String(c?.id || c?.label || `case_${i}`);
            const caseLabel = String(c?.label || `Case ${i + 1}`);
            return (
            <div key={caseId} className="flex items-center justify-end w-32 translate-x-1">
              <span className="text-[6px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 max-w-[50px] truncate pointer-events-auto" title={caseLabel}>
                {caseLabel}
              </span>
              <Handle type="source" position={Position.Right} id={caseId} className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all pointer-events-auto ${isRunningLike ? '!bg-emerald-500' : '!bg-blue-400'}`} />
              <PlusButton handleId={caseId} className="-right-10" />
            </div>
          )})}
          <div className="flex items-center justify-end w-32 translate-x-1">
            <span className="text-[6px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm mr-2 pointer-events-auto">Default</span>
            <Handle type="source" position={Position.Right} id={defaultCaseHandle} className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-slate-500 transition-all pointer-events-auto ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-400'}`} />
            <PlusButton handleId={defaultCaseHandle} className="-right-10" />
          </div>
        </div>
      ) : data.type === 'ai_agent' ? (
        <>
          <Handle
            type="source"
            position={Position.Right}
            className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
            style={{ right: -4 }}
          />
          {/* Bottom handles for AI Agent sub-nodes */}
          <div className="absolute -bottom-4 left-0 right-0 flex justify-around px-2 pointer-events-none">
            <div className="flex flex-col items-center gap-0.5 relative group/h">
              <Handle
                type="target"
                id="chat_model"
                position={Position.Bottom}
                style={{ position: 'static', rotate: '45deg' }}
                className="!w-2 !h-2 !rounded-none border border-white dark:border-slate-900 !bg-purple-500 hover:!bg-purple-400 pointer-events-auto"
              />
              <span className="text-[6px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-tighter">Chat Model*</span>
              <PlusButton handleId="chat_model" connectionType="target" className="-bottom-5" />
            </div>
            <div className="flex flex-col items-center gap-0.5 relative group/h">
              <Handle
                type="target"
                id="memory"
                position={Position.Bottom}
                style={{ position: 'static', rotate: '45deg' }}
                className="!w-2 !h-2 !rounded-none border border-white dark:border-slate-900 !bg-amber-500 hover:!bg-amber-400 pointer-events-auto"
              />
              <span className="text-[6px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-tighter">Memory</span>
              <PlusButton handleId="memory" connectionType="target" className="-bottom-5" />
            </div>
            <div className="flex flex-col items-center gap-0.5 relative group/h">
              <Handle
                type="target"
                id="tool"
                position={Position.Bottom}
                style={{ position: 'static', rotate: '45deg' }}
                className="!w-2 !h-2 !rounded-none border border-white dark:border-slate-900 !bg-emerald-500 hover:!bg-emerald-400 pointer-events-auto"
              />
              <span className="text-[6px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-tighter">Tool</span>
              <PlusButton handleId="tool" connectionType="target" className="-bottom-5" />
            </div>
          </div>
        </>
      ) : data.type === 'chat_model_openai' || data.type === 'chat_model_groq' ? (
        <>
          <div className="absolute -top-1 left-0 right-0 flex justify-center pointer-events-none">
            <Handle
              type="source"
              position={Position.Top}
              style={{ position: 'static', rotate: '45deg' }}
              className="!w-2 !h-2 !rounded-none border border-white dark:border-slate-900 !bg-purple-500 hover:!bg-purple-400 pointer-events-auto shadow-sm"
            />
          </div>
          <Handle
            type="target"
            position={Position.Left}
            className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
            style={{ left: -4 }}
          />
          <Handle
            type="source"
            position={Position.Right}
            className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
            style={{ right: -4 }}
          />
          <PlusButton handleId={null} className="-right-3 top-1/2 -translate-y-1/2" />
        </>
      ) : (
        <>
          <Handle
            type="source"
            position={Position.Right}
            className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
            style={{ right: -4 }}
          />
          <PlusButton handleId={null} className="-right-8 top-1/2 -translate-y-1/2" />
        </>
      )}
    </div>
  );
};

export default memo(BaseNode);
