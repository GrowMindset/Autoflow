import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';
import { WorkflowNode } from '../../types/workflow';
import JsonTree from './JsonTree';
import ConfigForm from './ConfigForm';
import { executionService } from '../../services/executionService';
import api from '../../services/api';

interface ConfigPanelProps {
  node: WorkflowNode;
  workflowId: string;
  upstreamData: any;
  onClose: () => void;
  onUpdate: (id: string, config: Record<string, any>, output?: any) => void;
}

const LogSection: React.FC<{ title: string; data: any; icon?: React.ReactNode }> = ({ title, data, icon }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center gap-2 px-1">
      {icon}
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{title}</span>
    </div>
    <div className="rounded-2xl border border-slate-100 bg-slate-50/50 p-2">
      {data ? <JsonTree data={data} /> : <span className="text-[10px] text-slate-300 italic px-2">No data recorded</span>}
    </div>
  </div>
);

const ConfigPanel: React.FC<ConfigPanelProps> = ({ node, workflowId, upstreamData, onClose, onUpdate }) => {
  const [output, setOutput] = useState<any>(node.data.last_output || null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isLeftVisible, setIsLeftVisible] = useState(true);
  const [isRightVisible, setIsRightVisible] = useState(true);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  const formFields = useMemo(
    () => Array.isArray(node.data.config?.fields) ? node.data.config.fields : [],
    [node.data.config],
  );

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

  const testUrl = useMemo(() => {
    if (!workflowId || workflowId === 'new') return '';
    const baseUrl = String(api.defaults.baseURL || '').replace(/\/$/, '');
    return `${baseUrl}/workflows/${workflowId}/run-form`;
  }, [workflowId]);

  const webhookUrl = useMemo(() => {
    if (!workflowId || workflowId === 'new') return '';
    const baseUrl = String(api.defaults.baseURL || '').replace(/\/$/, '');
    const path = node.data.config?.path || 'your-path';
    return `${baseUrl}/webhook/${workflowId}/${path.replace(/^\//, '')}`;
  }, [workflowId, node.data.config?.path]);

  // Sync state if node changes externally
  const handleConfigChange = (key: string, value: any) => {
    const nextConfig = { ...node.data.config, [key]: value };
    onUpdate(node.id, nextConfig);
  };

  const handleExecute = async () => {
    if (!workflowId || workflowId === 'new') {
      toast.error('Save the workflow first to test node execution.');
      return;
    }

    setIsExecuting(true);
    try {
      // If it's a form trigger, we should use the test form values as the input data
      const testInput = node.data.type === 'form_trigger' ? formValues : upstreamData;
      const enqueue = await executionService.executeNode(workflowId, node.id, testInput);

      let executionDetail = null;
      // Poll for 15 seconds
      for (let attempt = 0; attempt < 15; attempt += 1) {
        await new Promise((r) => setTimeout(r, 1000));
        executionDetail = await executionService.getExecution(enqueue.execution_id);

        const nodeResult = executionDetail.node_results.find(
          (result: any) => result.node_id === node.id
        );

        if (nodeResult && nodeResult.status !== 'PENDING' && nodeResult.status !== 'RUNNING') {
          if (nodeResult.status === 'SUCCEEDED') {
            setOutput(nodeResult.output_data);
            onUpdate(node.id, node.data.config, nodeResult.output_data);
            toast.success('Node executed successfully!');
          } else {
            setOutput({ error: nodeResult.error_message });
            toast.error(`Node execution failed: ${nodeResult.error_message}`);
          }
          break;
        }
      }
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

  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 md:p-8 animate-in fade-in zoom-in-95 duration-300">
      <div className="bg-white dark:bg-slate-900 w-full h-[92vh] max-w-[1700px] rounded-[2.5rem] shadow-[0_40px_100px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden border border-white/20 dark:border-slate-800 transition-colors duration-300">

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
                <h2 className="text-base font-black text-slate-800 dark:text-slate-100 tracking-tight">{node.data.label}</h2>
                {node.data.status && (
                  <span className={`text-[9px] font-black px-2 py-0.5 rounded-full text-white uppercase tracking-widest
                    ${node.data.status === 'SUCCEEDED' ? 'bg-emerald-500' :
                      node.data.status === 'FAILED' ? 'bg-rose-500' :
                        node.data.status === 'RUNNING' ? 'bg-blue-500 animate-pulse' : 'bg-slate-300'}
                  `}>
                    {node.data.status}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">{node.data.type}</span>
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
          <div className={`flex flex-col border-r border-slate-100 dark:border-slate-800 transition-all duration-500 ease-in-out bg-white dark:bg-slate-900 ${isLeftVisible ? 'w-[350px] opacity-100' : 'w-12 opacity-80'}`}>
            <div className="h-12 px-4 flex items-center justify-between border-b border-slate-50 dark:border-slate-800 bg-white dark:bg-slate-900 group select-none">
              {isLeftVisible ? (
                <>
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                    {node.data.last_execution_result ? 'EXECUTION LOGS' : 'INPUT DATA'}
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
                {node.data.last_execution_result ? (
                  <div className="space-y-6">
                    <div className="flex flex-col gap-1.5 p-3 rounded-2xl bg-slate-50 border border-slate-100">
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">Status</span>
                        <span className={`text-[8px] font-black uppercase tracking-widest ${node.data.last_execution_result.status === 'SUCCEEDED' ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {node.data.last_execution_result.status}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">Started At</span>
                        <span className="text-[8px] font-mono text-slate-500">{new Date(node.data.last_execution_result.started_at).toLocaleTimeString()}</span>
                      </div>
                      {node.data.last_execution_result.finished_at && (
                        <div className="flex items-center justify-between">
                          <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">Finished At</span>
                          <span className="text-[8px] font-mono text-slate-500">{new Date(node.data.last_execution_result.finished_at).toLocaleTimeString()}</span>
                        </div>
                      )}
                    </div>

                    <LogSection title="Execution Input" data={node.data.last_execution_result.input_data} />

                    {node.data.last_execution_result.error_message && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-rose-500">Error Message</span>
                        <div className="p-3 rounded-2xl bg-rose-50 border border-rose-100 text-[10px] text-rose-600 font-mono leading-relaxed">
                          {node.data.last_execution_result.error_message}
                        </div>
                      </div>
                    )}
                  </div>
                ) : upstreamData ? (
                  <JsonTree data={upstreamData} />
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
          </div>

          {/* Column 2: Parameters Form */}
          <div className="flex-1 flex flex-col overflow-hidden bg-white dark:bg-slate-900 z-10 shadow-[0_0_50px_rgba(0,0,0,0.02)]">
            <div className="h-12 px-8 flex items-center border-b border-slate-50 dark:border-slate-800 bg-white dark:bg-slate-900">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">PARAMETERS</span>
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
                        <h3 className="text-sm font-black text-slate-800">Webhook URL</h3>
                        <p className="text-xs text-slate-500">Send an HTTP {node.data.config?.method || 'POST'} request to this endpoint to trigger the workflow.</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-xs text-slate-600 break-all select-all">
                          {webhookUrl || 'Save the workflow to generate the Webhook URL.'}
                        </div>
                        <button 
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(webhookUrl);
                            toast.success('Copied to clipboard');
                          }}
                          disabled={!webhookUrl}
                          className="px-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50 font-bold text-xs"
                        >
                          Copy
                        </button>
                      </div>
                    </section>
                  </div>
                )}

                {node.data.type === 'form_trigger' && (
                  <div className="mt-10 space-y-8">
                    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-6">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <h3 className="text-sm font-black text-slate-800 dark:text-slate-100">Test URL</h3>
                          <p className="text-xs text-slate-500 dark:text-slate-500">Use this authenticated endpoint to submit test form data into the workflow.</p>
                        </div>
                      </div>
                      <div className="mt-4 flex items-center gap-2">
                        <div className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-xs text-slate-600 break-all select-all">
                          {testUrl || 'Save the workflow to generate the test URL.'}
                        </div>
                        <button 
                          className="px-4 py-3 bg-white border border-slate-200 rounded-2xl text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50 font-bold text-xs"
                          disabled={!testUrl}
                          onClick={() => {
                            navigator.clipboard.writeText(testUrl);
                            toast.success('Copied test URL');
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
              </div>
            </div>
          </div>

          {/* Column 3: Output Data / Execution Result */}
          <div className={`flex flex-col border-l border-slate-100 dark:border-slate-800 transition-all duration-500 ease-in-out bg-white dark:bg-slate-900 ${isRightVisible ? 'w-[400px] opacity-100' : 'w-12 opacity-80'}`}>
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
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                    {node.data.last_execution_result ? 'EXECUTION OUTPUT' : 'OUTPUT DATA'}
                  </span>
                </>
              )}
            </div>
            {isRightVisible && (
              <div className="flex-1 overflow-auto custom-scrollbar p-4 animate-in slide-in-from-right-4 duration-300">
                {node.data.last_execution_result ? (
                  <div className="space-y-6">
                    <LogSection title="Result Payload" data={node.data.last_execution_result.output_data} />
                  </div>
                ) : output ? (
                  <JsonTree data={output} />
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
          </div>

        </div>
      </div>
    </div>,
    document.body
  );
};

export default ConfigPanel;
