import React, { memo, useEffect, useMemo, useState } from 'react';
import { Handle, Position, NodeProps, useUpdateNodeInternals, useReactFlow, useEdges } from 'reactflow';
import { Check, Loader2, AlertCircle, AlertTriangle, Plus, Power } from 'lucide-react';
import { WorkflowNodeData } from '../../types/workflow';
import { CATEGORY_ACCENTS } from '../../constants/nodeLibrary';
import NodeBadge from '../sidebar/NodeBadge';
import { getNodeCountdownLabel, shouldShowLiveNodeCountdown } from '../../utils/nodeTimers';
import { toUserFriendlyErrorMessage } from '../../utils/errorMessages';

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
    'switch': ['field'],
    'filter': ['input_key', 'field', 'operator', 'value'],
    'get_gmail_message': ['credential_id'],
    'send_gmail_message': ['credential_id', 'to', 'subject', 'body'],
    'create_gmail_draft': ['credential_id', 'to', 'subject', 'body'],
    'add_gmail_label': ['credential_id', 'message_id', 'label_name'],
    'create_google_sheets': ['credential_id', 'title'],
    'file_read': ['file_path'],
    'file_write': ['file_path'],
    'create_google_docs': ['credential_id', 'title'],
    'read_google_docs': ['credential_id'],
    'update_google_docs': ['credential_id', 'document_id', 'operation'],
    'telegram': ['credential_id'],
    'whatsapp': ['credential_id', 'to_number', 'template_name'],
    'ai_agent': ['command'],
    'image_gen': ['credential_id', 'model', 'prompt', 'size'],
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
    const rawConditions = Array.isArray(config.conditions) && config.conditions.length > 0
      ? config.conditions
      : [{
          field: config.field,
          operator: config.operator,
          value: config.value,
          value_mode: config.value_mode,
          value_field: config.value_field,
        }];
    rawConditions.forEach((condition: any, index: number) => {
      if (!String(condition?.field || '').trim()) {
        missing.push(`Condition ${index + 1}: field is required`);
      }
      if (!String(condition?.operator || '').trim()) {
        missing.push(`Condition ${index + 1}: operator is required`);
      }
      const valueMode = String(condition?.value_mode || 'literal').toLowerCase() === 'field'
        ? 'field'
        : 'literal';
      if (valueMode === 'field') {
        if (!String(condition?.value_field || '').trim()) {
          missing.push(`Condition ${index + 1}: value_field is required`);
        }
      } else {
        const conditionValue = condition?.value;
        const hasLiteral = conditionValue !== undefined && conditionValue !== null && String(conditionValue).trim() !== '';
        if (!hasLiteral) {
          missing.push(`Condition ${index + 1}: value is required`);
        }
      }
    });
  }

  if (type === 'update_google_docs' && config.operation === 'replace_all_text' && !config.match_text) {
    missing.push("Required field 'match_text' is missing for replace_all_text operation");
  }
  if (type === 'update_google_docs' && !String(config.text || '').trim() && !String(config.image || '').trim()) {
    missing.push("Provide either 'text' or 'image'");
  }
  if (type === 'read_google_docs') {
    const sourceType = String(config.document_source_type || 'id').trim().toLowerCase();
    if (sourceType === 'url') {
      if (!String(config.document_url || '').trim()) {
        missing.push("Required field 'document_url' is missing for document_source_type='url'");
      }
    } else if (!String(config.document_id || '').trim()) {
      missing.push("Required field 'document_id' is missing");
    }
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
    const waitModeRaw = String(config.wait_mode || '').trim().toLowerCase();
    const waitMode = (
      waitModeRaw === 'after_interval'
      || waitModeRaw === 'until_datetime'
    )
      ? waitModeRaw
      : (String(config.until_datetime || '').trim() ? 'until_datetime' : 'after_interval');
    if (waitMode === 'after_interval') {
      const hasAmount = String(config.amount || '').trim() !== '';
      if (!hasAmount) {
        missing.push("Required field 'amount' is missing for wait_mode='after_interval'");
      }
      const unit = String(config.unit || '').trim().toLowerCase();
      if (!unit) {
        missing.push("Required field 'unit' is missing for wait_mode='after_interval'");
      }
    } else if (waitMode === 'until_datetime') {
      if (!String(config.until_datetime || '').trim()) {
        missing.push("Required field 'until_datetime' is missing for wait_mode='until_datetime'");
      }
    }
  }

  if (type === 'telegram' && !String(config.message || '').trim() && !String(config.image || '').trim()) {
    missing.push("Provide either 'message' or 'image'");
  }

  if (type === 'ai_agent' && !isChatModelConnected) {
    missing.push('Requires a Chat Model node connected to its bottom handle');
  }

  if (type === 'execute_workflow') {
    const source = String(config.source || 'database');
    if (source === 'json') {
      const rawJson = String(config.workflow_json || '').trim();
      if (!rawJson) {
        missing.push('Workflow Definition JSON is required');
      } else {
        try {
          JSON.parse(rawJson);
        } catch {
          missing.push('Workflow Definition JSON must be valid JSON');
        }
      }
    } else if (!String(config.workflow_id || '').trim()) {
      missing.push('Child Workflow is required');
    }
  }

  return missing;
};

const BaseNode: React.FC<NodeProps<WorkflowNodeData>> = ({ id, data, selected }) => {
  const accentColor = data.type === 'image_gen'
    ? '#f59e0b'
    : data.color
    ? data.color
    : ['get_gmail_message', 'send_gmail_message', 'create_gmail_draft', 'add_gmail_label'].includes(data.type)
    ? '#ea4335'
    : CATEGORY_ACCENTS[data.category] || '#cbd5e1';
  const updateNodeInternals = useUpdateNodeInternals();
  const { deleteElements } = useReactFlow();
  const edges = useEdges();

  const isChatModelConnected = edges.some(
    (e) => e.target === id && e.targetHandle === 'chat_model'
  );

  const missingReqs = getMissingRequirements(data.type, data.config, isChatModelConnected);
  const aiNodeErrorMessage = data.type === 'ai_agent' && data.status === 'FAILED'
    ? toUserFriendlyErrorMessage(data.last_execution_result?.error_message || '', '')
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
  const isNodeActive = data.is_active !== false;
  const canToggleActive = typeof data.onToggleActive === 'function';

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

  const handleToggleNodeActive = (e: React.MouseEvent) => {
    e.stopPropagation();
    data.onToggleActive?.(id);
  };

  // Notify React Flow when handles change (e.g. for Switch node cases)
  const caseIds = (data.config.cases || [])
    .map((c: any) => String(c?.id || c?.label || ''))
    .join(',');
  const defaultCaseHandle = String(data.config.default_case || 'default');
  const mergeInputCount = useMemo(() => {
    const raw = Number.parseInt(String(data.config?.input_count ?? ''), 10);
    if (!Number.isFinite(raw)) return 2;
    return Math.min(6, Math.max(2, raw));
  }, [data.config?.input_count]);
  const mergeInputHandles = useMemo(
    () => Array.from({ length: mergeInputCount }, (_, idx) => `input${idx + 1}`),
    [mergeInputCount],
  );
  const mergeIncomingEdgeCount = useMemo(
    () => edges.filter((edge) => edge.target === id).length,
    [edges, id],
  );
  const mergeInputGapMessage = data.type === 'merge' && mergeIncomingEdgeCount < mergeInputCount
    ? `Connect at least ${mergeInputCount} incoming branches.`
    : null;
  const allMissingReqs = mergeInputGapMessage ? [...missingReqs, mergeInputGapMessage] : missingReqs;
  const hasIncomplete = allMissingReqs.length > 0;
  const mergeHandleSignature = mergeInputHandles.join(',');
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, caseIds, defaultCaseHandle, mergeHandleSignature, updateNodeInternals]);
  
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

  const rawNote = String(data.config?.notes || '').trim();
  const notePreview = rawNote.length > 60 ? `${rawNote.slice(0, 60)}...` : rawNote;

  return (
    <div className="relative flex flex-col items-center">
      <div
        className={`px-3 py-2.5 rounded-xl border-2 transition-colors duration-200 shadow-none min-w-[150px] max-w-[150px] group/node relative 
        ${selected ? 'ring-2 ring-blue-500/10 border-blue-500' : 'border-slate-200 dark:border-slate-800'}
        ${isScheduleLive ? 'shadow-[0_0_20px_rgba(6,182,212,0.18)]' : ''}
        ${isRunningLike ? 'border-emerald-600 ring-[6px] ring-emerald-500/20 bg-emerald-50/30 dark:bg-emerald-900/10 animate-pulse' : ''}
        ${isSucceeded ? 'bg-emerald-50/30 dark:bg-emerald-500/5 border-emerald-500 shadow-[0_0_25px_rgba(16,185,129,0.2)] ring-[6px] ring-emerald-500/30' : 'bg-white dark:bg-slate-900'}
        ${isFailed ? 'bg-rose-50/30 dark:bg-rose-500/5 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.2)] ring-[6px] ring-rose-500/30' : ''}
        ${!isNodeActive && !isRunningLike && !isSucceeded && !isFailed ? 'bg-slate-100 dark:bg-slate-900/70 border-slate-300 dark:border-slate-700 opacity-70' : ''}
      `}
        style={{
          borderTop: `6px solid ${isRunningLike || isSucceeded ? '#10b981' :
            isFailed ? '#f43f5e' :
              isScheduleLive ? '#06b6d4' :
              !isNodeActive ? '#94a3b8' :
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
          title={`INCOMPLETE CONFIGURATION:\n• ${allMissingReqs.join('\n• ')}`}
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

      {canToggleActive && (
        <button
          onClick={handleToggleNodeActive}
          title={isNodeActive ? 'Deactivate node' : 'Activate node'}
          className={`absolute -top-7 left-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 transition-all flex items-center justify-center shadow-sm z-30 opacity-0 group-hover/node:opacity-100 nodrag ${
            isNodeActive
              ? 'text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 hover:border-emerald-300 dark:hover:border-emerald-900'
              : 'text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 hover:border-blue-300 dark:hover:border-blue-900'
          }`}
        >
          <Power size={10} strokeWidth={2.5} />
        </button>
      )}

      {data.type !== 'merge' && (
        <Handle
          type="target"
          position={Position.Left}
          className={`!w-1.5 !h-1.5 border border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike || isSucceeded ? '!bg-emerald-500' :
              isFailed ? '!bg-rose-500' :
                '!bg-slate-200 dark:!bg-slate-700'
            }`}
          style={{ left: -4 }}
        />
      )}

      <div className="flex flex-col gap-1 mt-0.5">
        <div className="flex items-center justify-between gap-3">
          <span className={`text-[8px] font-black uppercase tracking-widest`} style={{
            color: isRunningLike || isSucceeded ? '#059669' :
              isFailed ? '#e11d48' :
                !isNodeActive ? '#64748b' :
                accentColor
          }}>
            {data.category}
          </span>
          {data.is_dummy && <NodeBadge variant="neutral">Soon</NodeBadge>}
        </div>

        <h3 className={`text-xs font-bold leading-tight truncate ${isRunningLike || isSucceeded ? 'text-emerald-900 dark:text-emerald-100' :
            isFailed ? 'text-rose-900 dark:text-rose-100' :
              !isNodeActive ? 'text-slate-500 dark:text-slate-400' :
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
              !isNodeActive ? 'border-slate-200 dark:border-slate-800/80' :
              'border-slate-50 dark:border-slate-800/50'
          } pt-1.5 text-[8px] font-bold uppercase tracking-tighter ${isRunningLike || isSucceeded ? 'text-emerald-600 dark:text-emerald-400' :
            isFailed ? 'text-rose-600 dark:text-rose-400' :
              !isNodeActive ? 'text-slate-400 dark:text-slate-500' :
              'text-slate-400 dark:text-slate-500'
          }`}>
          <span className="truncate max-w-[100px]">{data.type.replace('_', ' ')}</span>
          <div className={`w-1 h-1 rounded-full ${isRunningLike ? 'bg-emerald-500 animate-pulse' :
              isSucceeded ? 'bg-emerald-500' :
                isFailed ? 'bg-rose-500' :
                  !isNodeActive ? 'bg-slate-400 dark:bg-slate-500' :
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
      ) : data.type === 'merge' ? (
        <>
          <Handle
            type="source"
            position={Position.Right}
            className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 hover:!bg-blue-500 transition-all ${isRunningLike ? '!bg-emerald-500' : '!bg-slate-300 dark:!bg-slate-600'}`}
            style={{ right: -4 }}
          />
          {mergeInputHandles.map((handleId, index) => {
            const total = mergeInputHandles.length;
            const topPercent = total === 1
              ? 50
              : 18 + (index * (64 / (total - 1)));
            const colorClasses = [
              '!bg-indigo-400 hover:!bg-indigo-500',
              '!bg-teal-400 hover:!bg-teal-500',
              '!bg-amber-400 hover:!bg-amber-500',
              '!bg-fuchsia-400 hover:!bg-fuchsia-500',
              '!bg-sky-400 hover:!bg-sky-500',
              '!bg-lime-400 hover:!bg-lime-500',
            ];
            const colorClass = colorClasses[index % colorClasses.length];

            return (
              <div
                key={handleId}
                className="absolute -left-1 flex items-center justify-start w-28 pointer-events-none"
                style={{ top: `${topPercent}%` }}
              >
                <Handle
                  type="target"
                  id={handleId}
                  position={Position.Left}
                  className={`!w-2 !h-2 border-2 border-white dark:border-slate-900 transition-all pointer-events-auto ${isRunningLike ? '!bg-emerald-500' : colorClass}`}
                />
                <span className="text-[6px] font-black uppercase text-slate-400 dark:text-slate-400 bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-100 dark:border-slate-700 shadow-sm ml-2 pointer-events-auto">
                  Input {index + 1}
                </span>
                <PlusButton handleId={handleId} connectionType="target" className="-left-10" />
              </div>
            );
          })}
          <PlusButton handleId={null} className="-right-8 top-1/2 -translate-y-1/2" />
        </>
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
      {data.config?.display_note && rawNote && (
        <div
          className="nodrag mt-1 max-w-[190px] rounded-md border border-slate-200 bg-white/95 px-2 py-1 text-center text-[8px] font-semibold leading-snug text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-400"
          title={rawNote}
        >
          {notePreview}
        </div>
      )}
    </div>
  );
};

export default memo(BaseNode);
