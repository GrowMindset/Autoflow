import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Plus } from 'lucide-react';
import { CredentialItem, credentialService } from '../../services/credentialService';

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
    { key: 'method', label: 'HTTP Method', type: 'select', options: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'] }
  ],
  form_trigger: [
    { key: 'form_title', label: 'Form Title', type: 'text', placeholder: 'e.g. User Feedback' },
    { key: 'form_description', label: 'Form Description', type: 'text', placeholder: 'e.g. Please let us know what you think.' },
    { key: 'fields', label: 'Form Fields', type: 'form_fields' }
  ],
  workflow_trigger: [
    { key: 'source_workflow', label: 'Triggering Workflow', type: 'text', placeholder: 'e.g. main-sync-job' }
  ],
  // Action Schemas
  get_gmail_message: [
    {
      key: 'credential_id',
      label: 'Gmail Credential',
      type: 'credential_selector',
      appName: 'gmail',
      credentialLabel: 'Gmail App Password + Email',
      credentialPlaceholder: 'Gmail App Password (16 chars)',
      credentialKey: 'app_password',
      requiresEmail: true,
    },
    { key: 'folder', label: 'Mailbox Folder', type: 'text', placeholder: 'e.g. INBOX' },
    { key: 'query', label: 'Search Query', type: 'text', placeholder: 'e.g. invoice OR from:billing@example.com' },
    { key: 'limit', label: 'Max Messages', type: 'text', placeholder: 'e.g. 10' },
    { key: 'unread_only', label: 'Unread Only', type: 'boolean' },
    { key: 'include_body', label: 'Include Body', type: 'boolean' },
    { key: 'mark_as_read', label: 'Mark As Read', type: 'boolean' },
  ],
  send_gmail_message: [
    {
      key: 'credential_id',
      label: 'Gmail Credential',
      type: 'credential_selector',
      appName: 'gmail',
      credentialLabel: 'Gmail App Password + Email',
      credentialPlaceholder: 'Gmail App Password (16 chars)',
      credentialKey: 'app_password',
      requiresEmail: true,
    },
    { key: 'to', label: 'Recipient Email', type: 'text', placeholder: 'e.g. user@example.com' },
    { key: 'cc', label: 'CC', type: 'text', placeholder: 'e.g. manager@example.com' },
    { key: 'bcc', label: 'BCC', type: 'text', placeholder: 'e.g. audit@example.com' },
    { key: 'reply_to', label: 'Reply-To', type: 'text', placeholder: 'e.g. support@example.com' },
    { key: 'subject', label: 'Subject', type: 'text', placeholder: 'e.g. Hello from Autoflow' },
    { key: 'body', label: 'Message Body', type: 'textarea', placeholder: 'Type your message here...' },
    { key: 'is_html', label: 'Send As HTML', type: 'boolean' },
  ],
  create_google_sheets: [
    {
      key: 'credential_id',
      label: 'Google Sheets Credential',
      type: 'credential_selector',
      appName: 'sheets',
      credentialLabel: 'Service Account JSON',
      credentialPlaceholder: 'Paste service-account JSON',
      credentialKey: 'service_account_json',
      requiresServiceAccountJson: true,
    },
    { key: 'title', label: 'Spreadsheet Title', type: 'text', placeholder: 'e.g. New Outreach List' },
    { key: 'sheet_name', label: 'First Sheet Name', type: 'text', placeholder: 'e.g. Leads' }
  ],
  search_update_google_sheets: [
    {
      key: 'credential_id',
      label: 'Google Sheets Credential',
      type: 'credential_selector',
      appName: 'sheets',
      credentialLabel: 'Service Account JSON',
      credentialPlaceholder: 'Paste service-account JSON',
      credentialKey: 'service_account_json',
      requiresServiceAccountJson: true,
    },
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', type: 'text', placeholder: 'e.g. 1aBC...xyz' },
    { key: 'sheet_name', label: 'Sheet Name', type: 'text', placeholder: 'e.g. Sheet1' },
    { key: 'search_column', label: 'Column to Search', type: 'text', placeholder: 'e.g. Email or A or 1' },
    { key: 'search_value', label: 'Value to Find', type: 'text', placeholder: 'e.g. {{ $json.email }}' },
    { key: 'update_column', label: 'Column to Update', type: 'text', placeholder: 'e.g. Status or D or 4' },
    { key: 'update_value', label: 'New Value', type: 'text', placeholder: 'e.g. Processed' }
  ],
  telegram: [
    {
      key: 'credential_id',
      label: 'Telegram Credential',
      type: 'credential_selector',
      appName: 'telegram',
      credentialLabel: 'Bot Token + Chat ID',
      credentialPlaceholder: 'Telegram Bot Token (e.g. 123456789:AA...)',
      credentialKey: 'api_key',
      requiresChatId: true,
    },
    {
      key: 'message',
      label: 'Message Text',
      type: 'textarea',
      placeholder: 'e.g. Order #{{ $json.id }} received!',
      helperText: 'Supports variable mapping and Telegram formatting.',
    },
    { key: 'parse_mode', label: 'Parse Mode', type: 'select', options: ['', 'HTML', 'Markdown', 'MarkdownV2'] },
  ],
  whatsapp: [
    {
      key: 'credential_id',
      label: 'WhatsApp Credential',
      type: 'credential_selector',
      appName: 'whatsapp',
      credentialLabel: 'Access Token',
      credentialPlaceholder: 'EAAxxxx...',
      credentialKey: 'access_token',
      requiresPhoneNumberId: true,
    },
    { key: 'to_number', label: 'Recipient Phone', type: 'text', placeholder: 'e.g. +919876543210' },
    { key: 'template_name', label: 'Template Name', type: 'text', placeholder: 'e.g. hello_world' },
    { key: 'template_params', label: 'Template Parameters', type: 'string_array' },
    { key: 'language_code', label: 'Language Code', type: 'text', placeholder: 'e.g. en_US' },
  ],
  linkedin: [
    { key: 'content', label: 'Post Content', type: 'text', placeholder: 'What do you want to share?' },
    { key: 'visibility', label: 'Visibility', type: 'select', options: ['PUBLIC', 'CONNECTIONS'] }
  ],
  ai_agent: [
    { key: 'system_prompt', label: 'System Prompt', type: 'textarea', placeholder: 'e.g. You are a helpful assistant...' },
    {
      key: 'command',
      label: 'User Prompt',
      type: 'textarea',
      placeholder: 'e.g. Summarize {{previous_output.field}} in one sentence.',
      helperText: 'Template syntax example: {{previous_output.field}}'
    }
  ],
  chat_model_openai: [
    { key: 'credential_id', label: 'Credential', type: 'credential_selector', appName: 'openai' },
    {
      key: 'model',
      label: 'Model',
      type: 'select',
      options: ['gpt-5-mini', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo']
    },
    { key: 'temperature', label: 'Temperature', type: 'text', placeholder: '0.7' }
  ],
  chat_model_groq: [
    { key: 'credential_id', label: 'Credential', type: 'credential_selector', appName: 'groq' },
    {
      key: 'model',
      label: 'Model',
      type: 'select',
      options: [
        // ── Production Models ──────────────────────────────
        'llama-3.3-70b-versatile',
        'llama-3.1-8b-instant',
        'openai/gpt-oss-120b',
        'openai/gpt-oss-20b',
        // ── Preview Models ─────────────────────────────────
        'meta-llama/llama-4-scout-17b-16e-instruct',
        'qwen/qwen3-32b',
      ]
    },
    { key: 'temperature', label: 'Temperature', type: 'text', placeholder: '0.7' }
  ]
};

interface ConfigFormProps {
  nodeType: string;
  config: Record<string, any>;
  onChange: (key: string, value: any) => void;
}

const ConfigForm: React.FC<ConfigFormProps> = ({ nodeType, config, onChange }) => {
  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeCredentialForm, setActiveCredentialForm] = useState<string | null>(null);
  const [newKey, setNewKey] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newChatId, setNewChatId] = useState('');
  const [newPhoneNumberId, setNewPhoneNumberId] = useState('');
  const [newServiceAccountJson, setNewServiceAccountJson] = useState('');
  const [dragOverField, setDragOverField] = useState<string | null>(null);

  // ── Drag-and-drop handlers for text/textarea fields ──────────────────────
  const handleDragOver = (e: React.DragEvent, fieldKey: string) => {
    // Always prevent default so the browser allows the drop.
    // (types.includes() on DOMStringList is unreliable cross-browser.)
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    if (dragOverField !== fieldKey) setDragOverField(fieldKey);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    // Only clear the highlight when leaving the element entirely,
    // not when the cursor moves to a child node inside it.
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragOverField(null);
    }
  };

  const handleDrop = (e: React.DragEvent, fieldKey: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverField(null);

    let textToInsert = '';

    // Check if dragging a literal value first
    const literalValue = e.dataTransfer.getData('application/json-value');
    if (literalValue) {
      textToInsert = literalValue;
    } else {
      const path = e.dataTransfer.getData('application/json-path');
      if (path) {
        textToInsert = `{{${path}}}`;
      } else {
        // Fallback for external drops
        textToInsert = e.dataTransfer.getData('text/plain') || '';
      }
    }

    if (!textToInsert) return;

    const el = e.currentTarget as HTMLInputElement | HTMLTextAreaElement;
    const current = String(config[fieldKey] || '');
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? start;
    onChange(fieldKey, current.slice(0, start) + textToInsert + current.slice(end));
  };

  const handleArrayDrop = (e: React.DragEvent, fieldKey: string, arrayRef: any[], index: number, itemKey: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverField(null);

    let textToInsert = '';
    const literalValue = e.dataTransfer.getData('application/json-value');
    if (literalValue) {
      textToInsert = literalValue;
    } else {
      const path = e.dataTransfer.getData('application/json-path');
      if (path) {
        textToInsert = `{{${path}}}`;
      } else {
        textToInsert = e.dataTransfer.getData('text/plain') || '';
      }
    }

    if (!textToInsert) return;

    const el = e.currentTarget as HTMLInputElement;
    const current = String(arrayRef[index][itemKey] || '');
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? start;
    
    const next = [...arrayRef];
    next[index] = { ...next[index], [itemKey]: current.slice(0, start) + textToInsert + current.slice(end) };
    onChange(fieldKey, next);
  };

  useEffect(() => {
    void fetchCredentials();
  }, [nodeType]);

  useEffect(() => {
    if (activeCredentialForm) {
      setNewKey('');
      setNewEmail('');
      setNewChatId('');
      setNewPhoneNumberId('');
      setNewServiceAccountJson('');
    }
  }, [activeCredentialForm]);

  const fetchCredentials = async () => {
    try {
      const list = await credentialService.list();
      setCredentials(list);
    } catch (err) {
      console.error('Failed to fetch credentials', err);
    }
  };

  const handleCreateCredential = async (
    appName: string,
    credentialKey: string = 'api_key',
    targetConfigKey: string = 'credential_id',
    extraTokenData: Record<string, string> = {},
    credentialValue?: string,
  ) => {
    const trimmed = String(credentialValue ?? newKey).trim();
    if (!trimmed) {
      toast.error('Please enter a credential value.');
      return;
    }
    if (credentialKey === 'service_account_json') {
      try {
        const parsed = JSON.parse(trimmed);
        if (!parsed || typeof parsed !== 'object') {
          toast.error('Service account JSON must be a valid JSON object.');
          return;
        }
        if (!String((parsed as any).client_email || '').trim()) {
          toast.error('Service account JSON is missing client_email.');
          return;
        }
        if (!String((parsed as any).private_key || '').trim()) {
          toast.error('Service account JSON is missing private_key.');
          return;
        }
      } catch {
        toast.error('Please paste valid service account JSON.');
        return;
      }
    }

    setLoading(true);
    try {
      const created = await credentialService.create({
        app_name: appName,
        token_data: { [credentialKey]: trimmed, ...extraTokenData },
      });

      onChange(targetConfigKey, created.id);
      setNewKey('');
      setNewEmail('');
      setNewChatId('');
      setNewPhoneNumberId('');
      setNewServiceAccountJson('');
      setActiveCredentialForm(null);
      await fetchCredentials();
      toast.success('Credential saved and selected.');
    } catch (err) {
      console.error('Failed to save credential', err);
      toast.error('Failed to save credential.');
    } finally {
      setLoading(false);
    }
  };

  const fields = CONFIG_SCHEMA[nodeType] || [];



  const renderField = (field: any) => {
    const value = config[field.key] ?? '';

    switch (field.type) {
      case 'select': {
        const selectOptions = field.dynamicOptionsBy
          ? (field.optionsByProvider?.[config[field.dynamicOptionsBy] || 'openai'] || [])
          : field.options;

        return (
          <select
            value={value}
            onChange={(e) => onChange(field.key, e.target.value)}
            className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
          >
            <option value="">Select option...</option>
            {selectOptions.map((opt: string) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );
      }

      case 'password':
        return (
          <input
            type="password"
            value={value}
            placeholder={field.placeholder}
            onChange={(e) => onChange(field.key, e.target.value)}
            className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
          />
        );

      case 'boolean':
        return (
          <select
            value={String(Boolean(value))}
            onChange={(e) => onChange(field.key, e.target.value === 'true')}
            className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
          >
            <option value="false">false</option>
            <option value="true">true</option>
          </select>
        );

      case 'array':
        const cases = Array.isArray(value) ? value : [];

        // Auto-migration: Ensure every case has a stable ID
        const casesWithIds = cases.map((c: any, idx: number) => {
          if (!c.id) {
            return { ...c, id: c.label || `case_${idx}` };
          }
          return c;
        });

        // Trigger update if we added missing IDs
        if (JSON.stringify(cases) !== JSON.stringify(casesWithIds)) {
          onChange(field.key, casesWithIds);
        }

        return (
          <div className="space-y-3">
            {casesWithIds.map((c: any, idx: number) => (
              <div key={c.id || idx} className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl space-y-2 relative group transition-colors">
                <button
                  onClick={() => {
                    const next = [...casesWithIds];
                    next.splice(idx, 1);
                    onChange(field.key, next);
                  }}
                  className="absolute top-2 right-2 text-slate-300 dark:text-slate-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Label"
                    value={c.label || ''}
                    onChange={(e) => {
                      const next = [...casesWithIds];
                      next[idx] = { ...c, label: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400 placeholder:text-slate-300 dark:placeholder:text-slate-700 transition-all"
                  />
                  <select
                    value={c.operator || ''}
                    onChange={(e) => {
                      const next = [...casesWithIds];
                      next[idx] = { ...c, operator: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400"
                  >
                    <option value="equals">equals</option>
                    <option value="contains">contains</option>
                  </select>
                </div>
                <div className="relative">
                  <input
                    type="text"
                    placeholder={dragOverField === `${field.key}_${idx}` ? 'Drop to insert…' : 'Value'}
                    value={c.value || ''}
                    onChange={(e) => {
                      const next = [...casesWithIds];
                      next[idx] = { ...c, value: e.target.value };
                      onChange(field.key, next);
                    }}
                    onDragOver={(e) => handleDragOver(e, `${field.key}_${idx}`)}
                    onDragLeave={(e) => handleDragLeave(e)}
                    onDrop={(e) => handleArrayDrop(e, field.key, casesWithIds, idx, 'value')}
                    className={`w-full bg-white dark:bg-slate-900 border rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === `${field.key}_${idx}`
                          ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                          : 'border-slate-200 dark:border-slate-700 focus:border-blue-500 dark:focus:border-blue-400'
                      }`}
                  />
                  {dragOverField === `${field.key}_${idx}` && (
                    <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none">
                      <span className="inline-flex items-center gap-1 bg-blue-500 text-white text-[10px] font-bold px-2 py-1 rounded shadow">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12l7 7 7-7" /></svg> Drop
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <button
              onClick={() => {
                const newId = `case_${Math.random().toString(36).substring(2, 9)}`;
                onChange(field.key, [...casesWithIds, { id: newId, label: `Case ${casesWithIds.length + 1}`, operator: 'equals', value: '' }]);
              }}
              className="w-full py-2 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 dark:text-slate-600 text-xs font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg>
              Add Case
            </button>
          </div>
        );

      case 'form_fields':
        const formFields = Array.isArray(value) ? value : [];
        return (
          <div className="space-y-3">
            {formFields.map((fieldDef: any, idx: number) => (
              <div key={idx} className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl space-y-3 relative transition-colors">
                <button
                  onClick={() => {
                    const next = [...formFields];
                    next.splice(idx, 1);
                    onChange(field.key, next);
                  }}
                  className="absolute top-2 right-2 text-slate-300 dark:text-slate-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Field name"
                    value={fieldDef.name || ''}
                    onChange={(e) => {
                      const next = [...formFields];
                      next[idx] = { ...fieldDef, name: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400 placeholder:text-slate-300 dark:placeholder:text-slate-700 transition-all"
                  />
                  <input
                    type="text"
                    placeholder="Label"
                    value={fieldDef.label || ''}
                    onChange={(e) => {
                      const next = [...formFields];
                      next[idx] = { ...fieldDef, label: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400 placeholder:text-slate-300 dark:placeholder:text-slate-700 transition-all"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={fieldDef.type || 'text'}
                    onChange={(e) => {
                      const next = [...formFields];
                      next[idx] = { ...fieldDef, type: e.target.value };
                      onChange(field.key, next);
                    }}
                    className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400"
                  >
                    <option value="text">text</option>
                    <option value="email">email</option>
                    <option value="number">number</option>
                    <option value="textarea">textarea</option>
                  </select>
                  <label className="flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs text-slate-600 dark:text-slate-400">
                    <input
                      type="checkbox"
                      checked={Boolean(fieldDef.required)}
                      onChange={(e) => {
                        const next = [...formFields];
                        next[idx] = { ...fieldDef, required: e.target.checked };
                        onChange(field.key, next);
                      }}
                    />
                    Required
                  </label>
                </div>
              </div>
            ))}
            <button
              onClick={() => onChange(field.key, [
                ...formFields,
                {
                  name: `field_${formFields.length + 1}`,
                  label: `Field ${formFields.length + 1}`,
                  type: 'text',
                  required: false,
                }
              ])}
              className="w-full py-2 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 dark:text-slate-600 text-xs font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg>
              Add Form Field
            </button>
          </div>
        );

      case 'string_array':
        const stringArray = Array.isArray(value) ? value : [];
        return (
          <div className="space-y-2">
            {stringArray.map((str: string, idx: number) => (
              <div key={idx} className="relative group">
                <input
                  type="text"
                  placeholder={dragOverField === `${field.key}_${idx}` ? 'Drop to insert…' : `Param ${idx + 1}`}
                  value={str || ''}
                  onChange={(e) => {
                    const next = [...stringArray];
                    next[idx] = e.target.value;
                    onChange(field.key, next);
                  }}
                  onDragOver={(e) => handleDragOver(e, `${field.key}_${idx}`)}
                  onDragLeave={(e) => handleDragLeave(e)}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDragOverField(null);
                    let textToInsert = '';
                    const literalValue = e.dataTransfer.getData('application/json-value');
                    if (literalValue) {
                      textToInsert = literalValue;
                    } else {
                      const path = e.dataTransfer.getData('application/json-path');
                      if (path) {
                        textToInsert = `{{${path}}}`;
                      } else {
                        textToInsert = e.dataTransfer.getData('text/plain') || '';
                      }
                    }
                    if (!textToInsert) return;
                    const el = e.currentTarget as HTMLInputElement;
                    const current = String(stringArray[idx] || '');
                    const start = el.selectionStart ?? current.length;
                    const end = el.selectionEnd ?? start;
                    const nextArr = [...stringArray];
                    nextArr[idx] = current.slice(0, start) + textToInsert + current.slice(end);
                    onChange(field.key, nextArr);
                  }}
                  className={`w-full bg-slate-50 dark:bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all pr-8 ${dragOverField === `${field.key}_${idx}`
                    ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                    : 'border-slate-200 dark:border-slate-700 focus:border-blue-500 dark:focus:border-blue-400'
                    }`}
                />
                <button
                  onClick={() => {
                    const next = [...stringArray];
                    next.splice(idx, 1);
                    onChange(field.key, next);
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
              </div>
            ))}
            <button
              onClick={() => onChange(field.key, [...stringArray, ''])}
              className="w-full py-1.5 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-lg text-slate-400 dark:text-slate-600 text-[10px] font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <Plus size={12} strokeWidth={3} />
              Add Parameter
            </button>
          </div>
        );

      case 'credential_selector':
        const filteredCreds = credentials.filter(c => c.app_name === field.appName);
        const credentialFormId = `${field.appName}:${field.key}`;
        const requiresChatId = Boolean(field.requiresChatId);
        const requiresEmail = Boolean(field.requiresEmail);
        const requiresPhoneNumberId = Boolean(field.requiresPhoneNumberId);
        const requiresServiceAccountJson = Boolean(field.requiresServiceAccountJson);
        const secretValue = requiresServiceAccountJson ? newServiceAccountJson : newKey;
        return (
          <div className="space-y-2">
            <div className="flex gap-2">
              <select
                value={value}
                onChange={(e) => onChange(field.key, e.target.value)}
                className="flex-1 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
              >
                <option value="">Select credential...</option>
                {filteredCreds.map((c: any) => (
                  <option key={c.id} value={c.id}>{c.app_name} - {c.id.substring(0, 8)}...</option>
                ))}
              </select>
              <button
                onClick={() => {
                  void fetchCredentials();
                  setNewKey('');
                  setNewEmail('');
                  setNewChatId('');
                  setNewPhoneNumberId('');
                  setNewServiceAccountJson('');
                  setActiveCredentialForm((current) => (
                    current === credentialFormId ? null : credentialFormId
                  ));
                }}
                className="px-3 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg>
              </button>
            </div>
            {activeCredentialForm === credentialFormId && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-xl space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
                <label className="text-[9px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                  Add {field.appName} {field.credentialLabel || 'API Key'}
                </label>
                <div className="space-y-2">
                  {requiresServiceAccountJson ? (
                    <textarea
                      name={`credential-service-account-${credentialFormId}`}
                      autoComplete="off"
                      spellCheck={false}
                      rows={6}
                      placeholder={field.credentialPlaceholder || 'Paste Google service account JSON'}
                      value={newServiceAccountJson}
                      onChange={(e) => setNewServiceAccountJson(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 font-mono resize-y"
                    />
                  ) : (
                    <input
                      type="password"
                      name={`credential-secret-${credentialFormId}`}
                      autoComplete="new-password"
                      spellCheck={false}
                      placeholder={field.credentialPlaceholder || 'sk-...'}
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500"
                    />
                  )}
                  {requiresEmail && (
                    <input
                      type="email"
                      name={`credential-email-${credentialFormId}`}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="Gmail Address (e.g. yourname@gmail.com)"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500"
                    />
                  )}
                  {requiresChatId && (
                    <input
                      type="text"
                      name={`credential-chat-id-${credentialFormId}`}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="Telegram Chat ID (e.g. 123456789 or -1001234567890)"
                      value={newChatId}
                      onChange={(e) => setNewChatId(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500"
                    />
                  )}
                  {requiresPhoneNumberId && (
                    <input
                      type="text"
                      name={`credential-phone-number-id-${credentialFormId}`}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="Phone Number ID (from Meta Business Suite)"
                      value={newPhoneNumberId}
                      onChange={(e) => setNewPhoneNumberId(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500"
                    />
                  )}
                  <button
                    disabled={loading || !secretValue.trim() || (requiresEmail && !newEmail.trim()) || (requiresChatId && !newChatId.trim()) || (requiresPhoneNumberId && !newPhoneNumberId.trim())}
                    onClick={() => {
                      const extraData: Record<string, string> = {};
                      if (requiresEmail) {
                        extraData.email = newEmail.trim();
                      }
                      if (requiresChatId) {
                        extraData.chat_id = newChatId.trim();
                      }
                      if (requiresPhoneNumberId) {
                        extraData.phone_number_id = newPhoneNumberId.trim();
                      }
                      void handleCreateCredential(
                        field.appName,
                        field.credentialKey || 'api_key',
                        field.key,
                        extraData,
                        secretValue,
                      );
                    }}
                    className="px-3 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-lg disabled:opacity-50 hover:bg-blue-700 transition-colors"
                  >
                    {loading ? '...' : 'Save'}
                  </button>
                </div>
              </div>
            )}
          </div>
        );

      case 'textarea':
        return (
          <div className="relative">
            <textarea
              value={value}
              placeholder={dragOverField === field.key ? 'Drop to insert {{path}}…' : field.placeholder}
              onChange={(e) => onChange(field.key, e.target.value)}
              onDragOver={(e) => handleDragOver(e, field.key)}
              onDragLeave={(e) => handleDragLeave(e)}
              onDrop={(e) => handleDrop(e, field.key)}
              rows={4}
              className={`w-full bg-slate-50 dark:bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 shadow-sm resize-y ${dragOverField === field.key
                  ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                  : 'border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                }`}
            />
            {dragOverField === field.key && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-lg">
                <span className="inline-flex items-center gap-1.5 bg-blue-500 text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow-lg">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M12 5v14M5 12l7 7 7-7" />
                  </svg>
                  Drop to insert
                </span>
              </div>
            )}
          </div>
        );

      case 'text':
      default:
        return (
          <div className="relative">
            <input
              type="text"
              value={value}
              placeholder={dragOverField === field.key ? 'Drop to insert {{path}}…' : field.placeholder}
              onChange={(e) => onChange(field.key, e.target.value)}
              onDragOver={(e) => handleDragOver(e, field.key)}
              onDragLeave={(e) => handleDragLeave(e)}
              onDrop={(e) => handleDrop(e, field.key)}
              className={`w-full bg-slate-50 dark:bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 shadow-sm ${dragOverField === field.key
                  ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                  : 'border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                }`}
            />
            {dragOverField === field.key && (
              <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none">
                <span className="inline-flex items-center gap-1 bg-blue-500 text-white text-[10px] font-bold px-2 py-1 rounded shadow">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M12 5v14M5 12l7 7 7-7" />
                  </svg>
                  Drop
                </span>
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <div className="space-y-6">
      {fields.length === 0 ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 dark:text-slate-700 gap-3">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-20"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" /><polyline points="14 2 14 8 20 8" /></svg>
          <span className="text-sm font-medium">No configuration available for this node type.</span>
        </div>
      ) : (
        fields.map((field) => (
          <div key={field.key} className="space-y-2">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-600 flex items-center justify-between">
              {field.label}
              {(field.type === 'text' || field.type === 'textarea') && (
                <span className="text-[9px] font-medium lowercase text-slate-300 dark:text-slate-700 normal-case">Supports mapping</span>
              )}
            </label>
            {renderField(field)}
            {field.helperText && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400">{field.helperText}</p>
            )}
          </div>
        ))
      )}
    </div>
  );
};

export default ConfigForm;
