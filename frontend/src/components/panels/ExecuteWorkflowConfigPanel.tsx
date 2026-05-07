import React, { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { Plus, X } from 'lucide-react';
import { workflowService } from '../../services/workflowService';

interface ExecuteWorkflowConfigPanelProps {
  config: Record<string, any>;
  workflowId: string;
  onChange: (key: string, value: any) => void;
  onChangePatch?: (patch: Record<string, any>) => void;
}

const makeInputRow = () => ({
  key: '',
  value: '',
});

const ExecuteWorkflowConfigPanel: React.FC<ExecuteWorkflowConfigPanelProps> = ({
  config,
  workflowId,
  onChange,
  onChangePatch,
}) => {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [dragOverInputIndex, setDragOverInputIndex] = useState<number | null>(null);
  const source = String(config.source || 'database');
  const mode = String(config.mode || 'run_once');
  const workflowInputs = Array.isArray(config.workflow_inputs) ? config.workflow_inputs : [];

  useEffect(() => {
    let isMounted = true;
    setLoadingWorkflows(true);
    workflowService.getWorkflows(100, 0)
      .then((items) => {
        if (isMounted) {
          setWorkflows(items.filter((workflow) => String(workflow.id) !== String(workflowId)));
        }
      })
      .finally(() => {
        if (isMounted) setLoadingWorkflows(false);
      });
    return () => {
      isMounted = false;
    };
  }, [workflowId]);

  const jsonValidationMessage = useMemo(() => {
    if (source !== 'json') return '';
    const rawJson = String(config.workflow_json || '').trim();
    if (!rawJson) return 'Workflow Definition JSON is required.';
    try {
      JSON.parse(rawJson);
      return '';
    } catch {
      return 'Workflow Definition JSON must be valid JSON.';
    }
  }, [config.workflow_json, source]);

  const updateInputs = (nextRows: any[]) => {
    onChange('workflow_inputs', nextRows);
  };

  const resolveDropText = (dataTransfer: DataTransfer) => {
    const literalValue = dataTransfer.getData('application/json-value');
    if (literalValue) return literalValue;

    const path = dataTransfer.getData('application/json-path');
    if (path) return `{{${path}}}`;

    return dataTransfer.getData('text/plain') || '';
  };

  const handleValueDragOver = (event: React.DragEvent, index: number) => {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
    if (dragOverInputIndex !== index) {
      setDragOverInputIndex(index);
    }
  };

  const handleValueDragLeave = (event: React.DragEvent) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node)) {
      setDragOverInputIndex(null);
    }
  };

  const handleValueDrop = (event: React.DragEvent<HTMLInputElement>, index: number) => {
    event.preventDefault();
    event.stopPropagation();
    setDragOverInputIndex(null);

    const textToInsert = resolveDropText(event.dataTransfer);
    if (!textToInsert) return;

    const current = String(workflowInputs[index]?.value || '');
    const start = event.currentTarget.selectionStart ?? current.length;
    const end = event.currentTarget.selectionEnd ?? start;
    const nextRows = [...workflowInputs];
    nextRows[index] = {
      ...nextRows[index],
      value: current.slice(0, start) + textToInsert + current.slice(end),
    };
    updateInputs(nextRows);
  };

  const setSource = (nextSource: 'database' | 'json') => {
    onChangePatch?.({
      source: nextSource,
      workflow_id: nextSource === 'database' ? config.workflow_id || '' : '',
      workflow_json: nextSource === 'json' ? config.workflow_json || '' : '',
    });
    if (!onChangePatch) onChange('source', nextSource);
  };

  const validateJson = () => {
    if (!jsonValidationMessage) {
      toast.success('Workflow JSON is valid');
      return;
    }
    toast.error(jsonValidationMessage);
  };

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <label className="text-xs font-black uppercase tracking-widest text-slate-400">
          Workflow Source
        </label>
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
          {[
            { value: 'database', label: 'Database' },
            { value: 'json', label: 'Define JSON below' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setSource(option.value as 'database' | 'json')}
              className={`rounded-xl px-3 py-2 text-xs font-bold transition-colors ${
                source === option.value
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      {source === 'database' ? (
        <section className="space-y-3">
          <label className="text-xs font-black uppercase tracking-widest text-slate-400">
            Child Workflow
          </label>
          <select
            value={config.workflow_id || ''}
            onChange={(event) => onChange('workflow_id', event.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            <option value="">{loadingWorkflows ? 'Loading workflows...' : 'Select a child workflow'}</option>
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
          {!config.workflow_id && (
            <p className="text-xs text-rose-500">Select a child workflow before saving.</p>
          )}
        </section>
      ) : (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <label className="text-xs font-black uppercase tracking-widest text-slate-400">
              Workflow Definition JSON
            </label>
            <button
              type="button"
              onClick={validateJson}
              className="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-500 transition-colors hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              Validate JSON
            </button>
          </div>
          <textarea
            value={config.workflow_json || ''}
            onChange={(event) => onChange('workflow_json', event.target.value)}
            rows={10}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-xs text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            placeholder='{"nodes":[],"edges":[]}'
          />
          {jsonValidationMessage && (
            <p className="text-xs text-rose-500">{jsonValidationMessage}</p>
          )}
        </section>
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <label className="text-xs font-black uppercase tracking-widest text-slate-400">
            Workflow Inputs
          </label>
          <button
            type="button"
            onClick={() => updateInputs([...workflowInputs, makeInputRow()])}
            className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-500 transition-colors hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Input
          </button>
        </div>
        <div className="space-y-3">
          {workflowInputs.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-xs text-slate-400 dark:border-slate-700 dark:bg-slate-800/50">
              Add inputs to pass data into the child workflow.
            </div>
          ) : (
            workflowInputs.map((row: any, index: number) => (
              <div key={index} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <input
                  value={row?.key || ''}
                  onChange={(event) => {
                    const nextRows = [...workflowInputs];
                    nextRows[index] = { ...nextRows[index], key: event.target.value };
                    updateInputs(nextRows);
                  }}
                  className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                  placeholder="Key Name"
                />
                <input
                  value={row?.value || ''}
                  onChange={(event) => {
                    const nextRows = [...workflowInputs];
                    nextRows[index] = { ...nextRows[index], value: event.target.value };
                    updateInputs(nextRows);
                  }}
                  onDragOver={(event) => handleValueDragOver(event, index)}
                  onDragLeave={handleValueDragLeave}
                  onDrop={(event) => handleValueDrop(event, index)}
                  className={`min-w-0 rounded-2xl border px-3 py-2 text-sm text-slate-700 outline-none transition-all dark:text-slate-200 ${
                    dragOverInputIndex === index
                      ? 'border-blue-400 bg-blue-50/40 ring-2 ring-blue-500/30 dark:border-blue-500 dark:bg-blue-900/10'
                      : 'border-slate-200 bg-slate-50 focus:border-blue-500 dark:border-slate-700 dark:bg-slate-800'
                  }`}
                  placeholder={dragOverInputIndex === index ? 'Drop to insert {{path}}...' : '{{node_id.field}}'}
                />
                <button
                  type="button"
                  onClick={() => updateInputs(workflowInputs.filter((_: any, rowIndex: number) => rowIndex !== index))}
                  className="rounded-2xl border border-slate-200 bg-white p-2 text-slate-400 transition-colors hover:text-rose-500 dark:border-slate-700 dark:bg-slate-900"
                  title="Remove input"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))
          )}
        </div>
        <p className="text-xs text-slate-400">Values support template syntax like {'{{node_id.field}}'}.</p>
      </section>

      <section className="space-y-3">
        <label className="text-xs font-black uppercase tracking-widest text-slate-400">
          Execution Mode
        </label>
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
          {[
            { value: 'run_once', label: 'Run once with all items' },
            { value: 'run_per_item', label: 'Run once for each item' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange('mode', option.value)}
              className={`rounded-xl px-3 py-2 text-xs font-bold transition-colors ${
                mode === option.value
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        {mode === 'run_per_item' && (
          <p className="text-xs text-slate-400">The input data must contain an array field.</p>
        )}
      </section>
    </div>
  );
};

export default ExecuteWorkflowConfigPanel;
