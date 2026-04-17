import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';
import { WorkflowNode } from '../../types/workflow';
import ConfigForm from './ConfigForm';
import LogSection from './LogSection';
import DataView from './DataView';
import { executionService } from '../../services/executionService';
import api from '../../services/api';
import { formatTimeInAppTimezone, getAppTimezone } from '../../utils/dateTime';

const DEFAULT_LEFT_PANEL_WIDTH = 350;
const DEFAULT_RIGHT_PANEL_WIDTH = 400;

interface ConfigPanelProps {
  node: WorkflowNode;
  workflowId: string;
  upstreamData: any;
  previousNodes: WorkflowNode[];
  nextNodes: WorkflowNode[];
  onClose: () => void;
  onUpdate: (id: string, config: Record<string, any>, output?: any) => void;
  onUpdateLabel?: (id: string, label: string) => void;
  onNavigateNode: (nodeId: string) => void;
  onExecutionEnqueued?: (payload: {
    executionId: string;
    nodeId: string;
    triggeredBy?: string;
  }) => void;
}

interface WebhookMeta {
  node_id: string;
  path_token: string;
  is_active: boolean;
  method: string;
  path: string;
  url: string;
}

const SCHEDULE_WEEKDAY_LABELS: Record<number, string> = {
  0: 'Sunday',
  1: 'Monday',
  2: 'Tuesday',
  3: 'Wednesday',
  4: 'Thursday',
  5: 'Friday',
  6: 'Saturday',
};

const toSafeInt = (rawValue: any, fallback: number) => {
  const value = Number.parseInt(String(rawValue ?? ''), 10);
  return Number.isFinite(value) ? value : fallback;
};

const getSchedulePreviewLines = (config: Record<string, any> | undefined) => {
  if (!config || typeof config !== 'object') return ['* * * * *'];

  const rawRules = Array.isArray(config.rules) ? config.rules : [];
  if (rawRules.length === 0) {
    const legacyCron = String(config.cron || '').trim();
    if (legacyCron) return [legacyCron];
    const minute = String(config.minute ?? '*').trim() || '*';
    const hour = String(config.hour ?? '*').trim() || '*';
    const dayOfMonth = String(config.day_of_month ?? '*').trim() || '*';
    const month = String(config.month ?? '*').trim() || '*';
    const dayOfWeek = String(config.day_of_week ?? '*').trim() || '*';
    return [`${minute} ${hour} ${dayOfMonth} ${month} ${dayOfWeek}`];
  }

  const lines: string[] = [];
  rawRules.forEach((rule: any, index: number) => {
    const interval = String(rule?.interval || '').trim().toLowerCase();
    const enabled = rule?.enabled !== false;
    const prefix = enabled ? `Rule ${index + 1}: ` : `Rule ${index + 1} (paused): `;

    if (interval === 'custom') {
      const cron = String(rule?.cron || '').trim() || '(missing cron)';
      lines.push(`${prefix}${cron}`);
      return;
    }

    if (interval === 'minutes') {
      const every = toSafeInt(rule?.every, 1);
      lines.push(`${prefix}Every ${every} minute(s)`);
      return;
    }

    if (interval === 'hours') {
      const every = toSafeInt(rule?.every, 1);
      const minute = toSafeInt(rule?.trigger_minute, 0);
      lines.push(`${prefix}Every ${every} hour(s) at minute ${minute}`);
      return;
    }

    if (interval === 'days') {
      const every = toSafeInt(rule?.every, 1);
      const hour = toSafeInt(rule?.trigger_hour, 9);
      const minute = toSafeInt(rule?.trigger_minute, 0);
      lines.push(`${prefix}Every ${every} day(s) at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
      return;
    }

    if (interval === 'weeks') {
      const every = toSafeInt(rule?.every, 1);
      const weekday = toSafeInt(rule?.trigger_weekday, 1);
      const hour = toSafeInt(rule?.trigger_hour, 9);
      const minute = toSafeInt(rule?.trigger_minute, 0);
      const weekdayLabel = SCHEDULE_WEEKDAY_LABELS[weekday] || `Weekday ${weekday}`;
      lines.push(`${prefix}Every ${every} week(s) on ${weekdayLabel} at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
      return;
    }

    if (interval === 'months') {
      const every = toSafeInt(rule?.every, 1);
      const day = toSafeInt(rule?.trigger_day_of_month, 1);
      const hour = toSafeInt(rule?.trigger_hour, 9);
      const minute = toSafeInt(rule?.trigger_minute, 0);
      lines.push(`${prefix}Every ${every} month(s) on day ${day} at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`);
      return;
    }

    lines.push(`${prefix}(unsupported interval)`);
  });
  return lines;
};


const ConfigPanel: React.FC<ConfigPanelProps> = ({
  node,
  workflowId,
  upstreamData,
  previousNodes,
  nextNodes,
  onClose,
  onUpdate,
  onUpdateLabel,
  onNavigateNode,
  onExecutionEnqueued,
}) => {
  const [output, setOutput] = useState<any>(node.data.last_output || null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLeftVisible, setIsLeftVisible] = useState(true);
  const [isRightVisible, setIsRightVisible] = useState(true);
  const [leftPanelWidth, setLeftPanelWidth] = useState(DEFAULT_LEFT_PANEL_WIDTH);
  const [rightPanelWidth, setRightPanelWidth] = useState(DEFAULT_RIGHT_PANEL_WIDTH);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);
  const [webhookMeta, setWebhookMeta] = useState<WebhookMeta | null>(null);
  const [webhookMetaLoading, setWebhookMetaLoading] = useState(false);
  const [openNavMenu, setOpenNavMenu] = useState<'prev' | 'next' | null>(null);
  const [editableLabel, setEditableLabel] = useState(node.data.label || '');
  const resizingSideRef = React.useRef<'left' | 'right' | null>(null);
  const resizeStartXRef = React.useRef(0);
  const resizeStartWidthRef = React.useRef(0);

  const formFields = useMemo(
    () => Array.isArray(node.data.config?.fields) ? node.data.config.fields : [],
    [node.data.config],
  );
  const schedulePreviewLines = useMemo(
    () => getSchedulePreviewLines(node.data.config),
    [node.data.config],
  );

  useEffect(() => {
    setOutput(node.data.last_output || null);
  }, [node.id, node.data.last_output]);

  useEffect(() => {
    setOpenNavMenu(null);
  }, [node.id]);

  useEffect(() => {
    setEditableLabel(node.data.label || '');
  }, [node.id, node.data.label]);

  useEffect(() => {
    if (node.data.type !== 'form_trigger') {
      setFormValues({});
      return;
    }

    setFormValues((prev) => {
      const next: Record<string, string> = {};
      formFields.forEach((field: any) => {
        if (!field?.name) return;
        next[field.name] = prev[field.name] ?? '';
      });
      return next;
    });
  }, [formFields, node.data.type]);

  const formPageUrl = useMemo(() => {
    if (!workflowId || workflowId === 'new') return '';
    const origin = window.location.origin.replace(/\/$/, '');
    return `${origin}/app/forms/${workflowId}?nodeId=${node.id}`;
  }, [workflowId, node.id]);

  const webhookConfiguredUrl = useMemo(() => {
    if (!workflowId || workflowId === 'new') return '';
    const baseUrl = String(api.defaults.baseURL || '').replace(/\/$/, '');
    const path = node.data.config?.path || 'your-path';
    return `${baseUrl}/webhook/${workflowId}/${path.replace(/^\//, '')}`;
  }, [workflowId, node.data.config?.path]);

  const webhookProductionUrl = webhookMeta?.url || '';
  const copyableWebhookUrl = webhookConfiguredUrl || webhookProductionUrl;

  const aiResponseText = useMemo(() => {
    if (node.data.type !== 'ai_agent') return null;

    const executionResponse =
      node.data.last_execution_result?.output_data?.output ||
      node.data.last_execution_result?.output_data?.ai_response;
    if (typeof executionResponse === 'string' && executionResponse.trim()) {
      return executionResponse;
    }

    const adHocResponse = output?.output || output?.ai_response;
    if (typeof adHocResponse === 'string' && adHocResponse.trim()) {
      return adHocResponse;
    }

    return null;
  }, [node.data.type, node.data.last_execution_result, output]);

  const aiErrorText = useMemo(() => {
    if (node.data.type !== 'ai_agent') return null;
    const executionError = node.data.last_execution_result?.error_message;
    if (executionError) return executionError;
    if (typeof output?.error === 'string' && output.error.trim()) return output.error;
    return null;
  }, [node.data.type, node.data.last_execution_result, output]);

  const shouldShowExecutionLogs = useMemo(() => {
    const result = node.data.last_execution_result;
    if (!result) return false;

    // During node-by-node testing, backend may return placeholder rows for
    // untouched nodes: status=PENDING and all payload/timestamps null.
    // In that case we should still show computed upstream input preview.
    const hasPayload =
      result.input_data !== null && typeof result.input_data !== 'undefined'
      || result.output_data !== null && typeof result.output_data !== 'undefined'
      || Boolean(result.error_message)
      || Boolean(result.started_at)
      || Boolean(result.finished_at);

    return result.status !== 'PENDING' || hasPayload;
  }, [node.data.last_execution_result]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizingSideRef.current) return;

      const delta = event.clientX - resizeStartXRef.current;
      if (resizingSideRef.current === 'left') {
        const nextWidth = Math.min(620, Math.max(240, resizeStartWidthRef.current + delta));
        setLeftPanelWidth(nextWidth);
      } else {
        const nextWidth = Math.min(700, Math.max(260, resizeStartWidthRef.current - delta));
        setRightPanelWidth(nextWidth);
      }
    };

    const handleMouseUp = () => {
      if (!resizingSideRef.current) return;
      resizingSideRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, []);

  useEffect(() => {
    if (node.data.type !== 'webhook_trigger') {
      setWebhookMeta(null);
      return;
    }
    if (!workflowId || workflowId === 'new') {
      setWebhookMeta(null);
      return;
    }

    const fetchWebhookMeta = async () => {
      setWebhookMetaLoading(true);
      try {
        const response = await api.get(`/workflows/${workflowId}/webhooks`);
        const webhooks = Array.isArray(response.data?.webhooks) ? response.data.webhooks : [];
        const current = webhooks.find((item: WebhookMeta) => item.node_id === node.id) || null;
        setWebhookMeta(current);
      } catch (error) {
        console.error('Failed to fetch webhook metadata', error);
        setWebhookMeta(null);
      } finally {
        setWebhookMetaLoading(false);
      }
    };

    void fetchWebhookMeta();
  }, [workflowId, node.id, node.data.type]);

  const handleResizeStart = (event: React.MouseEvent<HTMLDivElement>, side: 'left' | 'right') => {
    resizingSideRef.current = side;
    resizeStartXRef.current = event.clientX;
    resizeStartWidthRef.current = side === 'left' ? leftPanelWidth : rightPanelWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  // Sync state if node changes externally
  const handleConfigChange = (key: string, value: any) => {
    const nextConfig = { ...node.data.config, [key]: value };
    onUpdate(node.id, nextConfig);
  };

  const commitNodeLabelChange = () => {
    const nextLabel = editableLabel.trim();
    if (!nextLabel) {
      setEditableLabel(node.data.label || '');
      toast.error('Node name cannot be empty.');
      return;
    }
    if (nextLabel === node.data.label) return;
    onUpdateLabel?.(node.id, nextLabel);
  };

  const handleExecute = async () => {
    if (!workflowId || workflowId === 'new') {
      toast.error('Save the workflow first to test node execution.');
      return;
    }

    setIsExecuting(true);
    try {
      // If it's a form trigger, use test form values as input.
      const testInput = node.data.type === 'form_trigger' ? formValues : upstreamData;
      const enqueue = await executionService.executeNode(workflowId, node.id, testInput);
      onExecutionEnqueued?.({
        executionId: enqueue.execution_id,
        nodeId: node.id,
        triggeredBy: enqueue.triggered_by,
      });
      toast.success('Node execution started.');
    } catch (error: any) {
      console.error('Node execution failed:', error);
      toast.error(error.response?.data?.detail || 'Failed to trigger node execution');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleFormSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workflowId || workflowId === 'new') {
      toast.error('Save the workflow first to generate a testable form endpoint.');
      return;
    }

    setIsSubmittingForm(true);
    try {
      const enqueue = await executionService.runWorkflowForm(workflowId, {
        form_data: formValues,
        start_node_id: node.id,
      });

      let executionDetail = null;
      for (let attempt = 0; attempt < 8; attempt += 1) {
        const detail = await executionService.getExecution(enqueue.execution_id);
        if (detail.finished_at || detail.status === 'FAILED' || detail.status === 'SUCCEEDED') {
          executionDetail = detail;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 800));
      }

      const formNodeResult = executionDetail?.node_results?.find(
        (result: any) => result.node_id === node.id,
      );

      const nextOutput = executionDetail
        ? {
          enqueue,
          form_node: formNodeResult || null,
          execution: executionDetail,
        }
        : {
          enqueue,
          submitted_form_data: formValues,
        };

      setOutput(nextOutput);
      onUpdate(node.id, node.data.config, nextOutput);
      toast.success('Form test submitted.');
    } catch (error) {
      console.error('Form submission failed:', error);
    } finally {
      setIsSubmittingForm(false);
    }
  };

  const handleNavClick = (direction: 'prev' | 'next') => {
    const options = direction === 'prev' ? previousNodes : nextNodes;
    if (options.length === 0) return;
    if (options.length === 1) {
      onNavigateNode(options[0].id);
      return;
    }
    setOpenNavMenu((current) => (current === direction ? null : direction));
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 md:p-8 animate-in fade-in zoom-in-95 duration-300"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          setOpenNavMenu(null);
          onClose();
        }
      }}
    >
      <div className="relative w-full h-[92vh] max-w-[1700px]">

        {/* Side Navigation - vertically centered */}
        <div className="absolute inset-y-0 -left-14 md:-left-20 z-30 flex items-center pointer-events-none">
          <div className="relative pointer-events-auto">
            <button
              type="button"
              onClick={() => handleNavClick('prev')}
              disabled={previousNodes.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200/90 dark:border-slate-700/90 bg-white/95 dark:bg-slate-900/95 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-300 shadow-sm enabled:hover:border-blue-300 enabled:hover:text-blue-600 enabled:dark:hover:text-blue-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              title={previousNodes.length > 0 ? `Open previous node config (${previousNodes.length} upstream)` : 'No previous node connected'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
              Prev
              <span className="text-[9px] text-slate-400 dark:text-slate-500">({previousNodes.length})</span>
              {previousNodes.length > 1 && (
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
              )}
            </button>
            {openNavMenu === 'prev' && previousNodes.length > 1 && (
              <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 w-72 max-h-64 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl z-30 p-2">
                {previousNodes.map((connectedNode) => (
                  <button
                    key={connectedNode.id}
                    type="button"
                    onClick={() => {
                      onNavigateNode(connectedNode.id);
                      setOpenNavMenu(null);
                    }}
                    className="w-full text-left rounded-xl px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  >
                    <div className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{connectedNode.data.label}</div>
                    <div className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wide">{connectedNode.data.type}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="absolute inset-y-0 -right-14 md:-right-20 z-30 flex items-center pointer-events-none">
          <div className="relative pointer-events-auto">
            <button
              type="button"
              onClick={() => handleNavClick('next')}
              disabled={nextNodes.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200/90 dark:border-slate-700/90 bg-white/95 dark:bg-slate-900/95 text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-300 shadow-sm enabled:hover:border-blue-300 enabled:hover:text-blue-600 enabled:dark:hover:text-blue-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              title={nextNodes.length > 0 ? `Open next node config (${nextNodes.length} downstream)` : 'No next node connected'}
            >
              <span className="text-[9px] text-slate-400 dark:text-slate-500">({nextNodes.length})</span>
              Next
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
              {nextNodes.length > 1 && (
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
              )}
            </button>
            {openNavMenu === 'next' && nextNodes.length > 1 && (
              <div className="absolute right-full top-1/2 -translate-y-1/2 mr-2 w-72 max-h-64 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl z-30 p-2">
                {nextNodes.map((connectedNode) => (
                  <button
                    key={connectedNode.id}
                    type="button"
                    onClick={() => {
                      onNavigateNode(connectedNode.id);
                      setOpenNavMenu(null);
                    }}
                    className="w-full text-left rounded-xl px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  >
                    <div className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{connectedNode.data.label}</div>
                    <div className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wide">{connectedNode.data.type}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 w-full h-full rounded-[2.5rem] shadow-[0_40px_100px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden border border-white/20 dark:border-slate-800 transition-colors duration-300">

        {/* Header */}
        <div className="h-20 px-8 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 z-20">
          <div className="flex items-center gap-5">
            <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700 shadow-sm">
              <div className={`w-4 h-4 rounded-full ${node.data.category === 'trigger' ? 'bg-emerald-500' :
                node.data.category === 'action' ? 'bg-blue-500' :
                  node.data.category === 'transform' ? 'bg-amber-500' : 'bg-purple-500'
                } shadow-[0_0_10px_rgba(0,0,0,0.1)]`} />

              {node.data.status && (
                <div className={`absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white flex items-center justify-center
                  ${node.data.status === 'SUCCEEDED' ? 'bg-emerald-500' :
                    node.data.status === 'FAILED' ? 'bg-rose-500' :
                      node.data.status === 'RUNNING' ? 'bg-blue-500' : 'bg-slate-300'}
                `} />
              )}
            </div>
            <div>
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={editableLabel}
                  onChange={(event) => setEditableLabel(event.target.value)}
                  onBlur={commitNodeLabelChange}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      (event.currentTarget as HTMLInputElement).blur();
                    }
                    if (event.key === 'Escape') {
                      setEditableLabel(node.data.label || '');
                      (event.currentTarget as HTMLInputElement).blur();
                    }
                  }}
                  className="min-w-[220px] max-w-[460px] bg-transparent border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-blue-400 focus:ring-2 focus:ring-blue-500/20 rounded-lg px-2 py-1 text-base font-black text-slate-800 dark:text-slate-100 tracking-tight outline-none transition-all"
                  title="Editable node name"
                  placeholder="Node name"
                />
                {node.data.status && (
                  <span className={`text-[9px] font-black px-2 py-0.5 rounded-full text-white uppercase tracking-widest shadow-sm
                    ${node.data.status === 'SUCCEEDED' ? 'bg-emerald-500' :
                      node.data.status === 'FAILED' ? 'bg-rose-500' :
                        node.data.status === 'RUNNING' ? 'bg-blue-500 animate-pulse' : 'bg-slate-300'}
                  `}>
                    {node.data.status}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-400 dark:text-slate-400 uppercase tracking-widest bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">{node.data.type}</span>
                <span className="text-[10px] text-slate-300 dark:text-slate-600 font-mono">ID: {node.id.split('_').slice(0, 2).join('_')}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className={`flex items-center gap-2.5 px-6 py-2.5 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 rounded-2xl text-xs font-bold hover:bg-slate-800 dark:hover:bg-slate-200 transition-all shadow-[0_10px_20px_rgba(0,0,0,0.15)] active:scale-95 disabled:opacity-50 ${isExecuting ? 'animate-pulse' : ''}`}
            >
              {isExecuting ? 'Executing...' : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m5 3 14 9-14 9V3z" /></svg>
                  Execute Node
                </>
              )}
            </button>
            <div className="w-px h-8 bg-slate-100 dark:bg-slate-800 mx-2" />
            <button
              onClick={onClose}
              className="p-3 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-2xl transition-all text-slate-400 dark:text-slate-600 hover:text-slate-800 dark:hover:text-slate-200 active:bg-slate-200 dark:active:bg-slate-700"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
            </button>
          </div>
        </div>

        {/* 3-Column Layout */}
        <div className="flex-1 flex overflow-hidden relative bg-slate-50/20 dark:bg-slate-950/20">

          {/* Column 1: Input Data / Global Execution Logs */}
          <div
            className={`relative flex flex-col border-r border-slate-100 dark:border-slate-800 transition-all duration-300 ease-in-out bg-white dark:bg-slate-900 ${isLeftVisible ? 'opacity-100' : 'w-12 opacity-80'}`}
            style={isLeftVisible ? { width: `${leftPanelWidth}px` } : undefined}
          >
            <div className="h-12 px-4 flex items-center justify-between border-b border-slate-50 dark:border-slate-800 bg-white dark:bg-slate-900 group select-none">
              {isLeftVisible ? (
                <>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-400">
                    {shouldShowExecutionLogs ? 'EXECUTION LOGS' : 'INPUT DATA'}
                  </span>
                  <button onClick={() => setIsLeftVisible(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md text-slate-300 dark:text-slate-700 hover:text-slate-600 dark:hover:text-slate-400 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                  </button>
                </>
              ) : (
                <button onClick={() => setIsLeftVisible(true)} className="w-full h-full flex items-center justify-center hover:bg-slate-50 text-slate-300 hover:text-blue-500 transition-all">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                </button>
              )}
            </div>
            {isLeftVisible && (
              <div className="flex-1 overflow-auto custom-scrollbar p-4 animate-in slide-in-from-left-4 duration-300">
                {shouldShowExecutionLogs ? (
                  <div className="space-y-6">
                    <div className="flex flex-col gap-1.5 p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800">
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Status</span>
                        <span className={`text-[8px] font-black uppercase tracking-widest ${node.data.last_execution_result.status === 'SUCCEEDED' ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {node.data.last_execution_result.status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Started At</span>
                        <span className="text-[8px] font-mono text-slate-500 dark:text-slate-400">{formatTimeInAppTimezone(node.data.last_execution_result.started_at)}</span>
                      </div>
                      {node.data.last_execution_result.finished_at && (
                        <div className="flex items-center justify-between">
                          <span className="text-[8px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Finished At</span>
                          <span className="text-[8px] font-mono text-slate-500 dark:text-slate-400">{formatTimeInAppTimezone(node.data.last_execution_result.finished_at)}</span>
                        </div>
                      )}
                    </div>

                    <LogSection title="Execution Input" data={node.data.last_execution_result.input_data} />

                    {node.data.last_execution_result.error_message && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-rose-500">Error Message</span>
                        <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-100 dark:border-rose-900/30 text-[10px] text-rose-600 dark:text-rose-400 font-mono leading-relaxed">
                          {node.data.last_execution_result.error_message}
                        </div>
                      </div>
                    )}
                  </div>
                ) : upstreamData ? (
                  <DataView data={upstreamData} emptyMessage="No input data available" />
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-300 p-8 text-center space-y-4">
                    <div className="p-4 rounded-full bg-slate-50 border border-slate-100">
                      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="M12 11h4" /><path d="M12 16h4" /><path d="M8 11h.01" /><path d="M8 16h.01" /></svg>
                    </div>
                    <p className="text-xs font-medium leading-relaxed">No input data available. <br />Connect an upstream node.</p>
                  </div>
                )}
              </div>
            )}
            {isLeftVisible && (
              <div
                onMouseDown={(event) => handleResizeStart(event, 'left')}
                onDoubleClick={() => setLeftPanelWidth(DEFAULT_LEFT_PANEL_WIDTH)}
                className="group absolute top-0 right-0 h-full w-3 cursor-col-resize flex items-center justify-center bg-slate-100/60 dark:bg-slate-800/70 hover:bg-blue-500/10 active:bg-blue-500/20 transition-colors"
                title="Drag to resize input panel. Double-click to reset width."
              >
                <span className="h-14 w-[2px] rounded-full bg-slate-300 dark:bg-slate-600 group-hover:bg-blue-500 transition-colors" />
              </div>
            )}
          </div>

          {/* Column 2: Parameters Form */}
          <div className="flex-1 flex flex-col overflow-hidden bg-white dark:bg-slate-900 z-10 shadow-[0_0_50px_rgba(0,0,0,0.02)]">
            <div className="h-12 px-8 flex items-center border-b border-slate-50 dark:border-slate-800 bg-white dark:bg-slate-900">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-400">PARAMETERS</span>
            </div>
            <div className="flex-1 overflow-auto p-10 custom-scrollbar">
              <div className="max-w-2xl mx-auto pb-20">
                <ConfigForm
                  nodeType={node.data.type}
                  config={node.data.config}
                  onChange={handleConfigChange}
                />
                
                {node.data.type === 'webhook_trigger' && (
                  <div className="mt-10 space-y-8 animate-in fade-in slide-in-from-bottom-4">
                    <section className="rounded-3xl border border-slate-200 bg-slate-50 p-6 flex flex-col gap-4">
                      <div>
                        <h3 className="text-sm font-black text-slate-800 dark:text-slate-100">Configured Webhook URL</h3>
                        <p className="text-xs text-slate-500 dark:text-slate-500">
                          Send an HTTP {node.data.config?.method || webhookMeta?.method || 'POST'} request to this endpoint. This URL updates when you change the webhook path.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-xs text-slate-600 break-all select-all">
                          {webhookConfiguredUrl || 'Save the workflow to generate a webhook URL from the configured path.'}
                        </div>
                        <button 
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(copyableWebhookUrl);
                            toast.success('Copied to clipboard');
                          }}
                          disabled={!copyableWebhookUrl}
                          className="px-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50 font-bold text-xs"
                        >
                          Copy
                        </button>
                      </div>
                      {webhookMeta && (
                        <div className="text-[11px] text-slate-500 dark:text-slate-400">
                          Status: <span className={webhookMeta.is_active ? 'text-emerald-600 font-semibold' : 'text-amber-600 font-semibold'}>
                            {webhookMeta.is_active ? 'Active' : 'Inactive (publish workflow)'}
                          </span>
                        </div>
                      )}
                      {webhookMetaLoading && (
                        <div className="text-[11px] text-slate-500 dark:text-slate-400">Loading production webhook metadata...</div>
                      )}
                      {webhookProductionUrl && webhookProductionUrl !== webhookConfiguredUrl && (
                        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">Stable Production URL</p>
                          <p className="font-mono text-xs text-slate-500 break-all">{webhookProductionUrl}</p>
                        </div>
                      )}
                    </section>
                  </div>
                )}

                {node.data.type === 'form_trigger' && (
                  <div className="mt-10 space-y-8">
                    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-6">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <h3 className="text-sm font-black text-slate-800 dark:text-slate-100">Form Page URL</h3>
                          <p className="text-xs text-slate-500 dark:text-slate-500">Open this URL in a new tab to fill and submit the form on a dedicated page.</p>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <div className="min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-xs text-slate-600 break-all select-all">
                          {formPageUrl || 'Save the workflow to generate the form page URL.'}
                        </div>
                        <button
                          className="px-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50 font-bold text-xs"
                          disabled={!formPageUrl}
                          onClick={() => {
                            window.open(formPageUrl, '_blank', 'noopener,noreferrer');
                          }}
                        >
                          Open
                        </button>
                        <button
                          className="px-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50 font-bold text-xs"
                          disabled={!formPageUrl}
                          onClick={() => {
                            navigator.clipboard.writeText(formPageUrl);
                            toast.success('Copied form page URL');
                          }}
                        >
                          Copy
                        </button>
                      </div>
                    </section>

                    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/20 p-6 shadow-sm">
                      <div className="mb-5">
                        <h3 className="text-lg font-black text-slate-900 dark:text-slate-100">
                          {node.data.config?.form_title || 'Form Submission'}
                        </h3>
                        {node.data.config?.form_description ? (
                          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{node.data.config.form_description}</p>
                        ) : null}
                      </div>

                      <form className="space-y-4" onSubmit={handleFormSubmit}>
                        {formFields.length === 0 ? (
                          <div className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 px-4 py-6 text-sm text-slate-400 dark:text-slate-600">
                            Add at least one field above to test the form trigger.
                          </div>
                        ) : (
                          formFields.map((field: any, index: number) => {
                            const fieldName = field?.name || `field_${index + 1}`;
                            const label = field?.label || fieldName;
                            const inputType = field?.type === 'textarea' ? 'textarea' : (field?.type || 'text');
                            const value = formValues[fieldName] ?? '';

                            return (
                              <div key={`${fieldName}_${index}`} className="space-y-2">
                                <label className="text-xs font-black uppercase tracking-widest text-slate-400 dark:text-slate-600">
                                  {label}
                                  {field?.required ? ' *' : ''}
                                </label>
                                {inputType === 'textarea' ? (
                                  <textarea
                                    value={value}
                                    required={Boolean(field?.required)}
                                    onChange={(e) => setFormValues((prev) => ({ ...prev, [fieldName]: e.target.value }))}
                                    className="min-h-[110px] w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 px-4 py-3 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all focus:border-blue-500 dark:focus:border-blue-500 focus:bg-white dark:focus:bg-slate-800 shadow-sm"
                                  />
                                ) : (
                                  <input
                                    type={inputType}
                                    value={value}
                                    required={Boolean(field?.required)}
                                    onChange={(e) => setFormValues((prev) => ({ ...prev, [fieldName]: e.target.value }))}
                                    className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 px-4 py-3 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all focus:border-blue-500 dark:focus:border-blue-400 focus:bg-white dark:focus:bg-slate-800 shadow-sm"
                                  />
                                )}
                              </div>
                            );
                          })
                        )}

                        <button
                          type="submit"
                          disabled={isSubmittingForm || formFields.length === 0}
                          className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 dark:bg-slate-100 px-5 py-3 text-sm font-bold text-white dark:text-slate-900 transition-all hover:bg-slate-800 dark:hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50 shadow-lg"
                        >
                          {isSubmittingForm ? 'Submitting...' : 'Submit Test Form'}
                        </button>
                      </form>
                    </section>
                  </div>
                )}

                {node.data.type === 'schedule_trigger' && (
                  <div className="mt-10 space-y-8">
                    <section className="rounded-3xl border border-slate-200 bg-slate-50 p-6 flex flex-col gap-3">
                      <h3 className="text-sm font-black text-slate-800 dark:text-slate-100">Schedule Preview</h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        This trigger runs automatically when workflow is published and scheduler workers are running.
                      </p>
                      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 space-y-1">
                        {schedulePreviewLines.map((line, idx) => (
                          <div key={`${line}_${idx}`} className="font-mono text-xs text-slate-600 break-all">
                            {line}
                          </div>
                        ))}
                      </div>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        Timezone: {String(node.data.config?.timezone || getAppTimezone())}
                      </p>
                    </section>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Column 3: Output Data / Execution Result */}
          <div
            className={`relative flex flex-col border-l border-slate-100 dark:border-slate-800 transition-all duration-300 ease-in-out bg-white dark:bg-slate-900 ${isRightVisible ? 'opacity-100' : 'w-12 opacity-80'}`}
            style={isRightVisible ? { width: `${rightPanelWidth}px` } : undefined}
          >
            <div className="h-12 px-4 flex items-center justify-between border-b border-slate-50 dark:border-slate-800 bg-white dark:bg-slate-900 group select-none">
              {!isRightVisible ? (
                <button onClick={() => setIsRightVisible(true)} className="w-full h-full flex items-center justify-center hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-300 dark:text-slate-700 hover:text-blue-500 transition-all">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                </button>
              ) : (
                <>
                  <button onClick={() => setIsRightVisible(false)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md text-slate-300 dark:text-slate-700 hover:text-slate-600 dark:hover:text-slate-400 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                  </button>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-400">
                    {node.data.last_execution_result ? 'EXECUTION OUTPUT' : 'OUTPUT DATA'}
                  </span>
                </>
              )}
            </div>
            {isRightVisible && (
              <div className="flex-1 overflow-auto custom-scrollbar p-4 animate-in slide-in-from-right-4 duration-300">
                {node.data.last_execution_result ? (
                  <div className="space-y-6">
                    {node.data.type === 'ai_agent' && aiResponseText && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-blue-500">AI Response</span>
                        <div className="rounded-2xl border border-blue-100 dark:border-blue-900/30 bg-blue-50/60 dark:bg-blue-900/10 p-4">
                          <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-blue-900 dark:text-blue-100 font-mono">
                            {aiResponseText}
                          </pre>
                        </div>
                      </div>
                    )}

                    {node.data.type === 'ai_agent' && aiErrorText && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-rose-500">AI Error</span>
                        <div className="rounded-2xl border border-rose-200 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-900/20 p-3 text-xs text-rose-600 dark:text-rose-300 font-mono whitespace-pre-wrap break-words">
                          {aiErrorText}
                        </div>
                      </div>
                    )}
                    <LogSection title="Result Payload" data={node.data.last_execution_result.output_data} />
                  </div>
                ) : output ? (
                  <div className="space-y-6">
                    {node.data.type === 'ai_agent' && aiResponseText && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-blue-500">AI Response</span>
                        <div className="rounded-2xl border border-blue-100 dark:border-blue-900/30 bg-blue-50/60 dark:bg-blue-900/10 p-4">
                          <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed text-blue-900 dark:text-blue-100 font-mono">
                            {aiResponseText}
                          </pre>
                        </div>
                      </div>
                    )}

                    {node.data.type === 'ai_agent' && aiErrorText && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-rose-500">AI Error</span>
                        <div className="rounded-2xl border border-rose-200 dark:border-rose-900/30 bg-rose-50 dark:bg-rose-900/20 p-3 text-xs text-rose-600 dark:text-rose-300 font-mono whitespace-pre-wrap break-words">
                          {aiErrorText}
                        </div>
                      </div>
                    )}
                    <DataView data={output} emptyMessage="No output data recorded" />
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-300 p-8 text-center space-y-4">
                    <div className="p-4 rounded-full bg-slate-50 border border-slate-100">
                      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56" /><path d="M22 10 16 4" /><path d="m22 4-6 6" /></svg>
                    </div>
                    <p className="text-xs font-medium leading-relaxed">No output data yet. <br />Click 'Execute Node' to see results.</p>
                  </div>
                )}
              </div>
            )}
            {isRightVisible && (
              <div
                onMouseDown={(event) => handleResizeStart(event, 'right')}
                onDoubleClick={() => setRightPanelWidth(DEFAULT_RIGHT_PANEL_WIDTH)}
                className="group absolute top-0 left-0 h-full w-3 cursor-col-resize flex items-center justify-center bg-slate-100/60 dark:bg-slate-800/70 hover:bg-blue-500/10 active:bg-blue-500/20 transition-colors"
                title="Drag to resize output panel. Double-click to reset width."
              >
                <span className="h-14 w-[2px] rounded-full bg-slate-300 dark:bg-slate-600 group-hover:bg-blue-500 transition-colors" />
              </div>
            )}
          </div>

        </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default ConfigPanel;
