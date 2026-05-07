import React from 'react';
import { Plus, X } from 'lucide-react';

interface WorkflowTriggerConfigPanelProps {
  config: Record<string, any>;
  onChange: (key: string, value: any) => void;
}

const TYPE_OPTIONS = [
  { value: 'any', label: 'Allow any type' },
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'array', label: 'Array' },
  { value: 'object', label: 'Object' },
];

const WorkflowTriggerConfigPanel: React.FC<WorkflowTriggerConfigPanelProps> = ({
  config,
  onChange,
}) => {
  const mode = String(config.input_data_mode || 'accept_all');
  const inputSchema = Array.isArray(config.input_schema) ? config.input_schema : [];

  const updateSchema = (nextRows: any[]) => {
    onChange('input_schema', nextRows);
  };

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <label className="text-xs font-black uppercase tracking-widest text-slate-400">
          Input Data Mode
        </label>
        <div className="grid grid-cols-3 gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-800">
          {[
            { value: 'fields', label: 'Define using fields below' },
            { value: 'json_example', label: 'Define using JSON example' },
            { value: 'accept_all', label: 'Accept all data' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange('input_data_mode', option.value)}
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
      </section>

      {mode === 'fields' && (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <label className="text-xs font-black uppercase tracking-widest text-slate-400">
              Workflow Input Schema
            </label>
            <button
              type="button"
              onClick={() => updateSchema([...inputSchema, { name: '', type: 'any' }])}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-500 transition-colors hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Field
            </button>
          </div>
          <div className="space-y-3">
            {inputSchema.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-xs text-slate-400 dark:border-slate-700 dark:bg-slate-800/50">
                Add at least one accepted input field.
              </div>
            ) : (
              inputSchema.map((row: any, index: number) => (
                <div key={index} className="grid grid-cols-[1fr_160px_auto] gap-2">
                  <input
                    value={row?.name || ''}
                    onChange={(event) => {
                      const nextRows = [...inputSchema];
                      nextRows[index] = { ...nextRows[index], name: event.target.value };
                      updateSchema(nextRows);
                    }}
                    className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    placeholder="email"
                  />
                  <select
                    value={row?.type || 'any'}
                    onChange={(event) => {
                      const nextRows = [...inputSchema];
                      nextRows[index] = { ...nextRows[index], type: event.target.value };
                      updateSchema(nextRows);
                    }}
                    className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                  >
                    {TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => updateSchema(inputSchema.filter((_: any, rowIndex: number) => rowIndex !== index))}
                    className="rounded-2xl border border-slate-200 bg-white p-2 text-slate-400 transition-colors hover:text-rose-500 dark:border-slate-700 dark:bg-slate-900"
                    title="Remove field"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))
            )}
          </div>
          <p className="text-xs text-slate-400">Downstream nodes can reference these fields using {'{{$json.fieldName}}'}.</p>
        </section>
      )}

      {mode === 'json_example' && (
        <section className="space-y-3">
          <label className="text-xs font-black uppercase tracking-widest text-slate-400">
            JSON Example
          </label>
          <textarea
            value={config.json_example || ''}
            onChange={(event) => onChange('json_example', event.target.value)}
            rows={8}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-xs text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            placeholder='{ "email": "user@example.com", "status": "active" }'
          />
          <p className="text-xs text-slate-400">
            Paste an example of the JSON object this workflow will receive. Field names will be available as {'{{$json.fieldName}}'} in downstream nodes.
          </p>
        </section>
      )}

      {mode === 'accept_all' && (
        <section className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-4 text-sm text-blue-800 dark:border-blue-900/40 dark:bg-blue-900/20 dark:text-blue-100">
          This workflow will accept any input data passed to it. Access any field in downstream nodes using {'{{$json.fieldName}}'}.
        </section>
      )}
    </div>
  );
};

export default WorkflowTriggerConfigPanel;
