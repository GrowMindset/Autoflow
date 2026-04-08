import React from 'react';

/**
 * Schema defining the fields available for each node type.
 */
export const CONFIG_SCHEMA: Record<string, any[]> = {
  if_else: [
    { key: 'field', label: 'Field to evaluate', type: 'text', placeholder: 'e.g. status' },
    { 
      key: 'operator', 
      label: 'Operator', 
      type: 'select', 
      options: ['equals', 'not_equals', 'greater_than', 'less_than', 'contains', 'not_contains'] 
    },
    { key: 'value', label: 'Value to compare', type: 'text', placeholder: 'e.g. paid' }
  ],
  filter: [
    { key: 'input_key', label: 'Input Array Key', type: 'text', placeholder: 'e.g. items' },
    { key: 'field', label: 'Filter by field', type: 'text', placeholder: 'e.g. amount' },
    { 
      key: 'operator', 
      label: 'Operator', 
      type: 'select', 
      options: ['equals', 'not_equals', 'greater_than', 'less_than', 'contains', 'not_contains'] 
    },
    { key: 'value', label: 'Value', type: 'text', placeholder: 'e.g. 500' }
  ],
  aggregate: [
    { key: 'input_key', label: 'Input Array Key', type: 'text', placeholder: 'e.g. orders' },
    { key: 'field', label: 'Field to aggregate', type: 'text', placeholder: 'e.g. total' },
    { 
      key: 'operation', 
      label: 'Operation', 
      type: 'select', 
      options: ['sum', 'count', 'min', 'max', 'avg'] 
    },
    { key: 'output_key', label: 'Output Key Name', type: 'text', placeholder: 'e.g. result' }
  ],
  datetime_format: [
    { key: 'field', label: 'Date Field', type: 'text', placeholder: 'e.g. created_at' },
    { key: 'output_format', label: 'Target Format', type: 'text', placeholder: 'e.g. %Y-%m-%d' }
  ],
  switch: [
    { key: 'field', label: 'Field to evaluate', type: 'text', placeholder: 'e.g. country' },
    { key: 'cases', label: 'Routing Cases', type: 'array' },
    { key: 'default_case', label: 'Default Branch', type: 'text', placeholder: 'default' }
  ],
  split_in: [
    { key: 'input_key', label: 'Array to split', type: 'text', placeholder: 'e.g. items' }
  ],
  split_out: [
    { key: 'output_key', label: 'Results Key Name', type: 'text', placeholder: 'results' }
  ],
  // Trigger Schemas
  webhook_trigger: [
    { key: 'path', label: 'Webhook Path', type: 'text', placeholder: 'e.g. /my-webhook' },
    { key: 'method', label: 'HTTP Method', type: 'select', options: ['GET', 'POST', 'PUT', 'DELETE'] }
  ],
  form_trigger: [
    { key: 'form_title', label: 'Form Title', type: 'text', placeholder: 'e.g. User Feedback' },
    { key: 'form_description', label: 'Form Description', type: 'text', placeholder: 'e.g. Please let us know what you think.' }
  ],
  workflow_trigger: [
    { key: 'source_workflow', label: 'Triggering Workflow', type: 'text', placeholder: 'e.g. main-sync-job' }
  ],
  // Action Schemas
  get_gmail_message: [
    { key: 'query', label: 'Search Query', type: 'text', placeholder: 'e.g. from:support@google.com' },
    { key: 'limit', label: 'Max Messages', type: 'text', placeholder: 'e.g. 10' }
  ],
  send_gmail_message: [
    { key: 'to', label: 'Recipient Email', type: 'text', placeholder: 'e.g. user@example.com' },
    { key: 'subject', label: 'Subject', type: 'text', placeholder: 'e.g. Hello from Autoflow' },
    { key: 'body', label: 'Message Body', type: 'text', placeholder: 'Type your message here...' }
  ],
  create_google_sheets: [
    { key: 'title', label: 'Spreadsheet Title', type: 'text', placeholder: 'e.g. New Outreach List' }
  ],
  search_update_google_sheets: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', type: 'text', placeholder: 'e.g. 1aBC...xyz' },
    { key: 'sheet_name', label: 'Sheet Name', type: 'text', placeholder: 'e.g. Sheet1' },
    { key: 'search_column', label: 'Column to Search', type: 'text', placeholder: 'e.g. Email' },
    { key: 'search_value', label: 'Value to Find', type: 'text', placeholder: 'e.g. {{ $json.email }}' }
  ],
  telegram: [
    { key: 'chat_id', label: 'Chat ID', type: 'text', placeholder: 'e.g. 123456789' },
    { key: 'message', label: 'Message Text', type: 'text', placeholder: 'e.g. Order #{{ $json.id }} received!' }
  ],
  whatsapp: [
    { key: 'phone_number', label: 'Phone Number', type: 'text', placeholder: 'e.g. +1234567890' },
    { key: 'template_name', label: 'Message Template', type: 'text', placeholder: 'e.g. hello_world' }
  ],
  linkedin: [
    { key: 'content', label: 'Post Content', type: 'text', placeholder: 'What do you want to share?' },
    { key: 'visibility', label: 'Visibility', type: 'select', options: ['PUBLIC', 'CONNECTIONS'] }
  ],
  ai_agent: [
    { key: 'prompt', label: 'AI Instructions', type: 'text', placeholder: 'e.g. Summarize this text in 3 bullet points.' },
    { key: 'model', label: 'Model', type: 'select', options: ['gpt-4-turbo', 'gpt-3.5-turbo', 'claude-3-opus'] }
  ]
};

interface ConfigFormProps {
  nodeType: string;
  config: Record<string, any>;
  onChange: (key: string, value: any) => void;
}

const ConfigForm: React.FC<ConfigFormProps> = ({ nodeType, config, onChange }) => {
  const fields = CONFIG_SCHEMA[nodeType] || [];

  const handleDrop = (e: React.DragEvent, key: string) => {
    e.preventDefault();
    const path = e.dataTransfer.getData('application/json-path');
    if (path) {
      const expression = `{{ $json.${path} }}`;
      const currentValue = config[key] || '';
      onChange(key, currentValue + expression);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  const renderField = (field: any) => {
    const value = config[field.key] ?? '';

    switch (field.type) {
      case 'select':
        return (
          <select
            value={value}
            onChange={(e) => onChange(field.key, e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
          >
            <option value="">Select option...</option>
            {field.options.map((opt: string) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );

      case 'array':
        const cases = Array.isArray(value) ? value : [];
        return (
          <div className="space-y-3">
            {cases.map((c: any, idx: number) => (
              <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2 relative group">
                <button 
                  onClick={() => {
                    const next = [...cases];
                    next.splice(idx, 1);
                    onChange(field.key, next);
                  }}
                  className="absolute top-2 right-2 text-slate-300 hover:text-red-500 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Label"
                    value={c.label || ''}
                    onChange={(e) => {
                      const next = [...cases];
                      next[idx] = { ...c, label: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-blue-500"
                  />
                  <select
                    value={c.operator || ''}
                    onChange={(e) => {
                      const next = [...cases];
                      next[idx] = { ...c, operator: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-blue-500"
                  >
                    <option value="equals">equals</option>
                    <option value="contains">contains</option>
                  </select>
                </div>
                <input
                  type="text"
                  placeholder="Value"
                  value={c.value || ''}
                  onChange={(e) => {
                    const next = [...cases];
                    next[idx] = { ...c, value: e.target.value };
                    onChange(field.key, next);
                  }}
                  className="w-full bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-blue-500"
                />
              </div>
            ))}
            <button
              onClick={() => onChange(field.key, [...cases, { label: `case_${cases.length + 1}`, operator: 'equals', value: '' }])}
              className="w-full py-2 border-2 border-dashed border-slate-200 rounded-xl text-slate-400 text-xs font-bold hover:border-blue-300 hover:text-blue-500 transition-all flex items-center justify-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              Add Case
            </button>
          </div>
        );

      case 'text':
      default:
        return (
          <input
            type="text"
            value={value}
            placeholder={field.placeholder}
            onDrop={(e) => handleDrop(e, field.key)}
            onDragOver={handleDragOver}
            onChange={(e) => onChange(field.key, e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder:text-slate-300"
          />
        );
    }
  };

  return (
    <div className="space-y-6">
      {fields.length === 0 ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-3">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span className="text-sm">No configuration available for this node type.</span>
        </div>
      ) : (
        fields.map((field) => (
          <div key={field.key} className="space-y-2">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center justify-between">
              {field.label}
              {field.type === 'text' && (
                <span className="text-[9px] font-medium lowercase text-slate-300 normal-case">Supports mapping</span>
              )}
            </label>
            {renderField(field)}
          </div>
        ))
      )}
    </div>
  );
};

export default ConfigForm;
