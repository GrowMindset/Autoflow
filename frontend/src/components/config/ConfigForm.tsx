import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Plus } from 'lucide-react';
import { CredentialItem, credentialService } from '../../services/credentialService';
import { getAppTimezone } from '../../utils/dateTime';

const OAUTH_APPS = ['gmail', 'sheets', 'docs', 'linkedin'] as const;
const OAUTH_NODE_USAGE: Record<string, string[]> = {
  gmail: ['Get Gmail Message', 'Send Gmail Message'],
  sheets: ['Create Google Sheets', 'Search/Update Google Sheets'],
  docs: ['Create Google Docs', 'Update Google Docs'],
  linkedin: ['LinkedIn Post'],
};
const OAUTH_APP_LABEL: Record<string, string> = {
  gmail: 'Gmail',
  sheets: 'Google Sheets',
  docs: 'Google Docs',
  linkedin: 'LinkedIn',
};

const GoogleMark: React.FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
    <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.2-.9 2.2-1.8 2.9v2.4h2.9c1.7-1.6 2.7-4 2.7-7 0-.7-.1-1.4-.2-2H12z" />
    <path fill="#34A853" d="M12 21c2.4 0 4.4-.8 5.9-2.2l-2.9-2.4c-.8.6-1.8 1-3 1-2.3 0-4.2-1.5-4.9-3.6H4v2.3C5.5 19.1 8.5 21 12 21z" />
    <path fill="#4A90E2" d="M7.1 13.8c-.2-.6-.3-1.2-.3-1.8s.1-1.2.3-1.8V7.9H4C3.4 9.1 3 10.5 3 12s.4 2.9 1 4.1l3.1-2.3z" />
    <path fill="#FBBC05" d="M12 6.8c1.3 0 2.5.4 3.4 1.3l2.6-2.6C16.4 4 14.4 3 12 3 8.5 3 5.5 4.9 4 7.9l3.1 2.3c.7-2.1 2.6-3.4 4.9-3.4z" />
  </svg>
);

type ScheduleInterval = 'minutes' | 'hours' | 'days' | 'weeks' | 'months' | 'custom';

type ScheduleRule = {
  id: string;
  interval: ScheduleInterval;
  enabled: boolean;
  every?: number | string;
  trigger_minute?: number | string;
  trigger_hour?: number | string;
  trigger_weekday?: number | string;
  trigger_day_of_month?: number | string;
  cron?: string;
};

const SCHEDULE_INTERVAL_OPTIONS: Array<{ value: ScheduleInterval; label: string }> = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
  { value: 'months', label: 'Months' },
  { value: 'custom', label: 'Custom (Cron)' },
];

const SCHEDULE_WEEKDAY_OPTIONS = [
  { value: 0, label: 'Sunday' },
  { value: 1, label: 'Monday' },
  { value: 2, label: 'Tuesday' },
  { value: 3, label: 'Wednesday' },
  { value: 4, label: 'Thursday' },
  { value: 5, label: 'Friday' },
  { value: 6, label: 'Saturday' },
];

const SCHEDULE_LEGACY_KEYS = ['minute', 'hour', 'day_of_month', 'month', 'day_of_week'] as const;

const buildLegacyCronExpression = (rawConfig: Record<string, any>) => {
  const minute = String(rawConfig.minute ?? '*').trim() || '*';
  const hour = String(rawConfig.hour ?? '*').trim() || '*';
  const dayOfMonth = String(rawConfig.day_of_month ?? '*').trim() || '*';
  const month = String(rawConfig.month ?? '*').trim() || '*';
  const dayOfWeek = String(rawConfig.day_of_week ?? '*').trim() || '*';
  return `${minute} ${hour} ${dayOfMonth} ${month} ${dayOfWeek}`;
};

const isScheduleInterval = (value: string): value is ScheduleInterval =>
  ['minutes', 'hours', 'days', 'weeks', 'months', 'custom'].includes(value);

const makeScheduleRuleId = () => `rule_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

const createDefaultScheduleRule = (interval: ScheduleInterval = 'hours'): ScheduleRule => {
  const base: ScheduleRule = {
    id: makeScheduleRuleId(),
    interval,
    enabled: true,
  };

  switch (interval) {
    case 'minutes':
      return { ...base, every: 5 };
    case 'hours':
      return { ...base, every: 1, trigger_minute: 0 };
    case 'days':
      return { ...base, every: 1, trigger_hour: 9, trigger_minute: 0 };
    case 'weeks':
      return { ...base, every: 1, trigger_weekday: 1, trigger_hour: 9, trigger_minute: 0 };
    case 'months':
      return { ...base, every: 1, trigger_day_of_month: 1, trigger_hour: 9, trigger_minute: 0 };
    case 'custom':
    default:
      return { ...base, cron: '0 * * * *' };
  }
};

const PATH_STYLE_FIELD_KEYS = new Set([
  'field',
  'value_field',
  'input_key',
  'output_key',
]);

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

const SWITCH_CASE_OPERATORS = [
  'equals',
  'not_equals',
  'greater_than',
  'less_than',
  'contains',
  'not_contains',
];

const getDroppedPathValue = (path: string, fieldKey: string): string =>
  PATH_STYLE_FIELD_KEYS.has(fieldKey) ? path : `{{${path}}}`;

const normalizeSwitchCaseId = (rawCase: any, index: number): string => {
  const explicitId = String(rawCase?.id || '').trim();
  if (explicitId) return explicitId;
  const labelBased = String(rawCase?.label || '').trim();
  if (labelBased) return labelBased;
  return `case_${index + 1}`;
};

const normalizeScheduleRule = (rawRule: any, fallbackId?: string): ScheduleRule => {
  const rawObject: Partial<ScheduleRule> = rawRule && typeof rawRule === 'object' ? rawRule : {};
  const intervalRaw = String(rawRule?.interval || '').trim().toLowerCase();
  const interval: ScheduleInterval = isScheduleInterval(intervalRaw) ? intervalRaw : 'hours';
  const defaults = createDefaultScheduleRule(interval);
  return {
    ...defaults,
    ...rawObject,
    id: String(rawObject.id || fallbackId || defaults.id),
    interval,
    enabled: rawObject.enabled !== false,
  };
};

/**
 * Schema defining the fields available for each node type.
 */
export const CONFIG_SCHEMA: Record<string, any[]> = {
  if_else: [
    {
      key: 'condition',
      label: 'Condition Builder',
      type: 'if_condition',
      helperText: 'Compare one field with a literal value or another input field.',
    },
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
  schedule_trigger: [
    {
      key: 'enabled',
      label: 'Enabled',
      type: 'boolean',
      helperText: 'Disable to pause this schedule without removing the node.',
    },
    {
      key: 'rules',
      label: 'Trigger Rules',
      type: 'schedule_rules',
      helperText: 'Add one or more schedule rules. Use Custom (Cron) for advanced expressions.',
    },
    {
      key: 'timezone',
      label: 'Timezone',
      type: 'text',
      placeholder: 'e.g. Asia/Kolkata, UTC, America/New_York',
      helperText: 'IANA timezone name used for schedule matching.',
    },
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
      helperText: 'OAuth only: connect Gmail in Credential Manager, then select it here.',
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
      helperText: 'OAuth only: connect Gmail in Credential Manager, then select it here.',
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
      helperText: 'OAuth only: connect Google Sheets in Credential Manager, then select it here.',
    },
    { key: 'title', label: 'Spreadsheet Title', type: 'text', placeholder: 'e.g. New Outreach List' },
    { key: 'sheet_name', label: 'First Sheet Name', type: 'text', placeholder: 'e.g. Leads' },
    {
      key: 'columns',
      label: 'Column Headers',
      type: 'string_array',
      helperText: 'Optional: add headers (e.g. Name, Email, Status). They will be written to row 1.',
    },
  ],
  search_update_google_sheets: [
    {
      key: 'credential_id',
      label: 'Google Sheets Credential',
      type: 'credential_selector',
      appName: 'sheets',
      helperText: 'OAuth only: connect Google Sheets in Credential Manager, then select it here.',
    },
    {
      key: 'spreadsheet_source_type',
      label: 'Spreadsheet Source',
      type: 'select',
      options: ['id', 'url'],
    },
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', type: 'text', placeholder: 'e.g. 1aBC...xyz' },
    { key: 'spreadsheet_url', label: 'Spreadsheet URL', type: 'text', placeholder: 'https://docs.google.com/spreadsheets/d/...' },
    { key: 'sheet_name', label: 'Sheet Name (Tab)', type: 'text', placeholder: 'e.g. Sheet1' },
    {
      key: 'operation',
      label: 'Operation',
      type: 'select',
      options: ['append_row', 'delete_rows', 'overwrite_row', 'upsert_row', 'add_columns', 'delete_columns'],
    },
    { key: 'key_column', label: 'Key Column', type: 'text', placeholder: 'e.g. Email or A or 1' },
    { key: 'key_value', label: 'Key Value', type: 'text', placeholder: 'e.g. {{customer.email}}' },
    {
      key: 'append_columns',
      label: 'Append Columns',
      type: 'string_array',
      helperText: 'For append_row: column headers/letters/numbers in order.',
    },
    {
      key: 'append_values',
      label: 'Append Values',
      type: 'string_array',
      helperText: 'For append_row: value list aligned with Append Columns.',
    },
    {
      key: 'update_mappings',
      label: 'Columns to Update',
      type: 'sheet_update_mappings',
      helperText: 'For append_row / overwrite_row / upsert_row: one or more column/value pairs.',
    },
    {
      key: 'columns_to_add',
      label: 'Columns to Add',
      type: 'string_array',
      helperText: 'For add_columns operation.',
    },
    {
      key: 'columns_to_delete',
      label: 'Columns to Delete',
      type: 'string_array',
      helperText: 'For delete_columns operation. Uses header name, letter, or number.',
    },
    { key: 'auto_create_headers', label: 'Create Missing Columns Automatically', type: 'boolean' },
  ],
  create_google_docs: [
    {
      key: 'credential_id',
      label: 'Google Docs Credential',
      type: 'credential_selector',
      appName: 'docs',
      helperText: 'OAuth only: connect Google Docs in Credential Manager, then select it here.',
    },
    { key: 'title', label: 'Document Title', type: 'text', placeholder: 'e.g. Daily Report' },
    { key: 'initial_content', label: 'Initial Content', type: 'textarea', placeholder: 'Optional initial content...' },
  ],
  update_google_docs: [
    {
      key: 'credential_id',
      label: 'Google Docs Credential',
      type: 'credential_selector',
      appName: 'docs',
      helperText: 'OAuth only: connect Google Docs in Credential Manager, then select it here.',
    },
    { key: 'document_id', label: 'Document ID', type: 'text', placeholder: 'e.g. 1AbCdEf...' },
    {
      key: 'operation',
      label: 'Operation',
      type: 'select',
      options: ['append_text', 'replace_all_text'],
    },
    { key: 'text', label: 'Text', type: 'textarea', placeholder: 'Text to append or replace with...' },
    { key: 'match_text', label: 'Match Text (for replace)', type: 'text', placeholder: 'Required when operation=replace_all_text' },
    { key: 'match_case', label: 'Match Case', type: 'boolean' },
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
  slack_send_message: [
    {
      key: 'credential_id',
      label: 'Slack Credential',
      type: 'credential_selector',
      appName: 'slack',
      credentialLabel: 'Incoming Webhook URL',
      credentialPlaceholder: 'https://hooks.slack.com/services/T000/B000/XXXXXXXX',
      credentialKey: 'webhook_url',
      requiresChannel: true,
    },
    {
      key: 'message',
      label: 'Message Text',
      type: 'textarea',
      placeholder: 'e.g. Hello team! {{ $json.order_id }} is ready.',
      helperText: 'Supports variable mapping and Slack text formatting.',
    },
  ],
  delay: [
    { key: 'amount', label: 'Delay Amount', type: 'text', placeholder: 'e.g. 5' },
    {
      key: 'unit',
      label: 'Delay Unit',
      type: 'select',
      options: ['seconds', 'minutes', 'hours', 'days', 'months'],
      helperText: 'Used when "Run At (ISO datetime)" is empty.',
    },
    {
      key: 'until_datetime',
      label: 'Run At (ISO datetime)',
      type: 'text',
      placeholder: 'e.g. 2026-04-17T18:30:00Z',
      helperText: 'Optional. If set, this overrides amount + unit.',
    },
  ],
  linkedin: [
    {
      key: 'credential_id',
      label: 'LinkedIn Credential',
      type: 'credential_selector',
      appName: 'linkedin',
      credentialLabel: 'LinkedIn OAuth',
      credentialPlaceholder: 'Connect LinkedIn via OAuth',
      credentialKey: 'api_key',
    },
    { key: 'post_text', label: 'Post Content', type: 'textarea', placeholder: 'What do you want to share?' },
    {
      key: 'visibility',
      label: 'Visibility',
      type: 'select',
      options: ['PUBLIC', 'CONNECTIONS'],
      helperText: 'Choose who can see this post.',
    },
  ],
  http_request: [
    { key: 'url', label: 'URL', type: 'text', placeholder: 'https://api.example.com/v1/resource' },
    {
      key: 'method',
      label: 'HTTP Method',
      type: 'select',
      options: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'],
    },
    {
      key: 'auth_mode',
      label: 'Auth Mode',
      type: 'select',
      options: ['none', 'bearer', 'basic', 'api_key'],
    },
    {
      key: 'credential_id',
      label: 'HTTP Credential (Optional)',
      type: 'credential_selector',
      appName: 'http',
      credentialLabel: 'API Secret / Token',
      credentialPlaceholder: 'Paste token or API secret',
      credentialKey: 'api_key',
      helperText: 'Optional credential store for bearer/API key value.',
    },
    { key: 'bearer_token', label: 'Bearer Token (optional)', type: 'text', placeholder: 'eyJ...' },
    { key: 'bearer_prefix', label: 'Bearer Prefix', type: 'text', placeholder: 'Bearer' },
    { key: 'username', label: 'Basic Auth Username', type: 'text', placeholder: 'api-user' },
    { key: 'password', label: 'Basic Auth Password', type: 'text', placeholder: '••••••••' },
    { key: 'api_key_name', label: 'API Key Name', type: 'text', placeholder: 'x-api-key' },
    { key: 'api_key_value', label: 'API Key Value (optional)', type: 'text', placeholder: 'abc123' },
    {
      key: 'api_key_in',
      label: 'API Key Location',
      type: 'select',
      options: ['header', 'query'],
    },
    { key: 'api_key_prefix', label: 'API Key Prefix', type: 'text', placeholder: '' },
    {
      key: 'headers_json',
      label: 'Headers JSON',
      type: 'textarea',
      placeholder: '{"Accept":"application/json","Content-Type":"application/json"}',
    },
    {
      key: 'query_json',
      label: 'Query Params JSON',
      type: 'textarea',
      placeholder: '{"page":1,"limit":50}',
    },
    {
      key: 'body_type',
      label: 'Body Type',
      type: 'select',
      options: ['none', 'json', 'form', 'raw'],
    },
    {
      key: 'body_json',
      label: 'JSON Body',
      type: 'textarea',
      placeholder: '{"name":"Asha","status":"active"}',
    },
    {
      key: 'body_form_json',
      label: 'Form Body JSON',
      type: 'textarea',
      placeholder: '{"field1":"value1","field2":"value2"}',
    },
    { key: 'body_raw', label: 'Raw Body', type: 'textarea', placeholder: 'Raw body text...' },
    { key: 'timeout_seconds', label: 'Timeout (seconds)', type: 'text', placeholder: '30' },
    { key: 'follow_redirects', label: 'Follow Redirects', type: 'boolean' },
    { key: 'continue_on_fail', label: 'Continue On HTTP Error', type: 'boolean' },
    {
      key: 'response_format',
      label: 'Response Format',
      type: 'select',
      options: ['auto', 'json', 'text'],
    },
  ],
  file_read: [
    { key: 'file_path', label: 'File Path', type: 'text', placeholder: 'e.g. data/input.json' },
    {
      key: 'parse_as',
      label: 'Parse As',
      type: 'select',
      options: ['auto', 'text', 'json', 'csv', 'lines', 'base64'],
    },
    { key: 'encoding', label: 'Encoding', type: 'text', placeholder: 'utf-8' },
    { key: 'max_bytes', label: 'Max Bytes', type: 'text', placeholder: '5242880' },
    { key: 'csv_delimiter', label: 'CSV Delimiter', type: 'text', placeholder: ', or \\t (optional)' },
    { key: 'include_metadata', label: 'Include Metadata', type: 'boolean' },
  ],
  file_write: [
    { key: 'file_path', label: 'File Path', type: 'text', placeholder: 'e.g. data/output.json' },
    {
      key: 'content_source',
      label: 'Content Source',
      type: 'select',
      options: ['input', 'config'],
    },
    {
      key: 'input_key',
      label: 'Input Key (optional)',
      type: 'text',
      placeholder: 'e.g. report.content',
      helperText: 'Used when Content Source = input. Leave blank to use full input payload.',
    },
    {
      key: 'content_text',
      label: 'Content Text',
      type: 'textarea',
      placeholder: 'Used when Content Source = config.',
    },
    {
      key: 'input_format',
      label: 'Input Format',
      type: 'select',
      options: ['auto', 'text', 'json', 'base64'],
    },
    {
      key: 'write_mode',
      label: 'Write Mode',
      type: 'select',
      options: ['create', 'overwrite', 'append'],
    },
    { key: 'encoding', label: 'Encoding', type: 'text', placeholder: 'utf-8' },
    { key: 'create_dirs', label: 'Create Parent Dirs', type: 'boolean' },
  ],
  ai_agent: [
    { key: 'system_prompt', label: 'System Prompt', type: 'textarea', placeholder: 'e.g. You are a helpful assistant...' },
    {
      key: 'command',
      label: 'User Prompt',
      type: 'textarea',
      placeholder: 'e.g. Summarize {{previous_output.field}} in one sentence.',
      helperText: 'Template syntax example: {{previous_output.field}}'
    },
    {
      key: 'response_enhancement',
      label: 'Response Enhancement',
      type: 'select',
      options: ['auto', 'always', 'off'],
      helperText: 'auto = refine only weak responses, always = always polish, off = raw model output',
    },
  ],
  chat_model_openai: [
    { key: 'credential_id', label: 'Credential', type: 'credential_selector', appName: 'openai' },
    {
      key: 'model',
      label: 'Model',
      type: 'select',
      options: ['gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano']
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
  const [newChatId, setNewChatId] = useState('');
  const [newPhoneNumberId, setNewPhoneNumberId] = useState('');
  const [newChannel, setNewChannel] = useState('');
  const [dragOverField, setDragOverField] = useState<string | null>(null);
  const [oauthConnectingApp, setOauthConnectingApp] = useState<string | null>(null);

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
        textToInsert = getDroppedPathValue(path, fieldKey);
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
      setNewChatId('');
      setNewPhoneNumberId('');
      setNewChannel('');
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

    setLoading(true);
    try {
      const created = await credentialService.create({
        app_name: appName,
        token_data: { [credentialKey]: trimmed, ...extraTokenData },
      });

      onChange(targetConfigKey, created.id);
      setNewKey('');
      setNewChatId('');
      setNewPhoneNumberId('');
      setNewChannel('');
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

  const handleQuickGoogleOAuthConnect = async (appName: string) => {
    const normalizedApp = String(appName || '').trim().toLowerCase();
    if (!OAUTH_APPS.includes(normalizedApp as (typeof OAUTH_APPS)[number])) {
      return;
    }

    setOauthConnectingApp(normalizedApp);
    try {
      const redirectUri = normalizedApp === 'linkedin'
        ? `${window.location.origin}/app/oauth/linkedin/callback`
        : `${window.location.origin}/app/oauth/google/callback`;
      const result = normalizedApp === 'linkedin'
        ? await credentialService.startLinkedInOAuth(redirectUri)
        : await credentialService.startGoogleOAuth(
            normalizedApp as 'gmail' | 'sheets' | 'docs',
            redirectUri,
          );
      window.location.href = result.auth_url;
    } catch (error) {
      console.error('Failed to start OAuth:', error);
      toast.error(`Could not start ${OAUTH_APP_LABEL[normalizedApp] || 'OAuth'} flow.`);
      setOauthConnectingApp(null);
    }
  };

  useEffect(() => {
    if (nodeType !== 'search_update_google_sheets') return;

    const patch: Record<string, any> = {};
    const sourceTypeRaw = String(config.spreadsheet_source_type || '').trim().toLowerCase();
    if (!sourceTypeRaw) {
      patch.spreadsheet_source_type = String(config.spreadsheet_url || '').trim() ? 'url' : 'id';
    }

    if (typeof config.auto_create_headers === 'undefined') {
      patch.auto_create_headers = true;
    }

    if (!String(config.operation || '').trim()) {
      patch.operation = config.upsert_if_not_found ? 'upsert_row' : 'overwrite_row';
    } else {
      const normalizedOperation = normalizeSheetsOperation(config.operation, Boolean(config.upsert_if_not_found));
      if (normalizedOperation !== String(config.operation || '').trim().toLowerCase()) {
        patch.operation = normalizedOperation;
      }
    }

    if (!String(config.key_column || '').trim() && String(config.search_column || '').trim()) {
      patch.key_column = config.search_column;
    }
    if (!String(config.key_value || '').trim() && String(config.search_value || '').trim()) {
      patch.key_value = config.search_value;
    }

    if (!Array.isArray(config.append_columns)) {
      patch.append_columns = [];
    }
    if (!Array.isArray(config.append_values)) {
      patch.append_values = [];
    }
    if (!Array.isArray(config.columns_to_add)) {
      patch.columns_to_add = Array.isArray(config.ensure_columns) ? config.ensure_columns : [];
    }
    if (!Array.isArray(config.columns_to_delete)) {
      patch.columns_to_delete = [];
    }

    const operation = normalizeSheetsOperation(config.operation, Boolean(config.upsert_if_not_found));
    const hasMappings = Array.isArray(config.update_mappings)
      && config.update_mappings.some((item: any) => String(item?.column || item?.update_column || '').trim() !== '');
    const appendColumns = Array.isArray(config.append_columns) ? config.append_columns : [];
    const appendValues = Array.isArray(config.append_values) ? config.append_values : [];
    if (operation === 'append_row' && !hasMappings && appendColumns.length > 0) {
      const nextMappings = appendColumns
        .map((rawColumn: any, idx: number) => {
          const column = String(rawColumn || '').trim();
          if (!column) return null;
          return {
            id: `mapping_append_${idx}_${Math.random().toString(36).slice(2, 7)}`,
            column,
            value: idx < appendValues.length ? appendValues[idx] : '',
          };
        })
        .filter(Boolean);
      if (nextMappings.length > 0) {
        patch.update_mappings = nextMappings;
      }
    }

    Object.entries(patch).forEach(([key, value]) => {
      onChange(key, value);
    });
  }, [nodeType, config, onChange]);

  useEffect(() => {
    if (nodeType !== 'schedule_trigger') return;

    const patch: Record<string, any> = {};
    const timezone = String(config.timezone || '').trim();
    if (!timezone) {
      patch.timezone = getAppTimezone();
    }
    if (typeof config.enabled === 'undefined') {
      patch.enabled = true;
    }

    const rawRules = Array.isArray(config.rules) ? config.rules : [];
    if (rawRules.length > 0) {
      const normalizedRules = rawRules.map((rule, index) => normalizeScheduleRule(rule, `rule_${index + 1}`));
      if (JSON.stringify(rawRules) !== JSON.stringify(normalizedRules)) {
        patch.rules = normalizedRules;
      }
    } else {
      const explicitCron = String(config.cron || '').trim();
      const hasLegacyShape = SCHEDULE_LEGACY_KEYS.some((key) => key in config);
      if (explicitCron) {
        patch.rules = [normalizeScheduleRule({ interval: 'custom', cron: explicitCron, enabled: true })];
      } else if (hasLegacyShape) {
        patch.rules = [
          normalizeScheduleRule({
            interval: 'custom',
            cron: buildLegacyCronExpression(config),
            enabled: true,
          }),
        ];
      } else {
        patch.rules = [createDefaultScheduleRule('hours')];
      }
    }

    Object.entries(patch).forEach(([key, value]) => {
      onChange(key, value);
    });
  }, [
    nodeType,
    config,
    onChange,
  ]);

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

      case 'if_condition': {
        const fieldPath = String(config.field ?? '');
        const operator = String(config.operator || 'equals');
        const valueMode = String(config.value_mode || 'literal').toLowerCase() === 'field'
          ? 'field'
          : 'literal';
        const valueFieldPath = String(config.value_field ?? '');
        const compareValue = config.value ?? '';
        const caseSensitive = Boolean(config.case_sensitive ?? true);
        const usesStringComparison = ['equals', 'not_equals', 'contains', 'not_contains'].includes(operator);

        return (
          <div className="space-y-3 p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Left Field Path
              </label>
              <input
                type="text"
                value={fieldPath}
                placeholder={dragOverField === 'field' ? 'Drop to insert path…' : 'e.g. status or user.payment.status'}
                onChange={(event) => onChange('field', event.target.value)}
                onDragOver={(event) => handleDragOver(event, 'field')}
                onDragLeave={(event) => handleDragLeave(event)}
                onDrop={(event) => handleDrop(event, 'field')}
                className={`w-full bg-white dark:bg-slate-900 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === 'field'
                  ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                  : 'border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                  }`}
              />
            </div>

            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Operator
                </label>
                <select
                  value={operator}
                  onChange={(event) => onChange('operator', event.target.value)}
                  className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                >
                  <option value="equals">Equals</option>
                  <option value="not_equals">Not Equals</option>
                  <option value="greater_than">Greater Than</option>
                  <option value="less_than">Less Than</option>
                  <option value="contains">Contains</option>
                  <option value="not_contains">Not Contains</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Compare With
                </label>
                <select
                  value={valueMode}
                  onChange={(event) => onChange('value_mode', event.target.value)}
                  className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                >
                  <option value="literal">Literal Value</option>
                  <option value="field">Another Field</option>
                </select>
              </div>
            </div>

            {valueMode === 'field' ? (
              <div className="space-y-1">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Right Field Path
                </label>
                <input
                  type="text"
                  value={valueFieldPath}
                  placeholder={dragOverField === 'value_field' ? 'Drop to insert path…' : 'e.g. expected_status'}
                  onChange={(event) => onChange('value_field', event.target.value)}
                  onDragOver={(event) => handleDragOver(event, 'value_field')}
                  onDragLeave={(event) => handleDragLeave(event)}
                  onDrop={(event) => handleDrop(event, 'value_field')}
                  className={`w-full bg-white dark:bg-slate-900 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === 'value_field'
                    ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                    : 'border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                    }`}
                />
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Right Value
                </label>
                <input
                  type="text"
                  value={String(compareValue ?? '')}
                  placeholder={dragOverField === 'value' ? 'Drop to insert {{path}}…' : 'e.g. paid'}
                  onChange={(event) => onChange('value', event.target.value)}
                  onDragOver={(event) => handleDragOver(event, 'value')}
                  onDragLeave={(event) => handleDragLeave(event)}
                  onDrop={(event) => handleDrop(event, 'value')}
                  className={`w-full bg-white dark:bg-slate-900 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === 'value'
                    ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                    : 'border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                    }`}
                />
              </div>
            )}

            {usesStringComparison && (
              <div className="space-y-1">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Case Sensitive
                </label>
                <select
                  value={String(caseSensitive)}
                  onChange={(event) => onChange('case_sensitive', event.target.value === 'true')}
                  className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </div>
            )}
          </div>
        );
      }

      case 'schedule_rules': {
        const rawRules = Array.isArray(value) ? value : [];
        const normalizedRules = rawRules.length > 0
          ? rawRules.map((rule, index) => normalizeScheduleRule(rule, `rule_${index + 1}`))
          : [createDefaultScheduleRule('hours')];

        if (JSON.stringify(rawRules) !== JSON.stringify(normalizedRules)) {
          onChange(field.key, normalizedRules);
        }

        const updateRule = (index: number, patch: Record<string, any>) => {
          const next = [...normalizedRules];
          next[index] = { ...next[index], ...patch };
          onChange(field.key, next);
        };

        return (
          <div className="space-y-3">
            {normalizedRules.map((rule, idx) => {
              const interval = String(rule.interval || 'hours').toLowerCase() as ScheduleInterval;
              return (
                <div key={rule.id || idx} className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                      Trigger Interval {idx + 1}
                    </span>
                    {normalizedRules.length > 1 && (
                      <button
                        type="button"
                        onClick={() => {
                          const next = [...normalizedRules];
                          next.splice(idx, 1);
                          onChange(field.key, next);
                        }}
                        className="text-xs text-rose-500 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-300"
                      >
                        Remove
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Trigger Interval
                      </label>
                      <select
                        value={interval}
                        onChange={(event) => {
                          const nextInterval = event.target.value as ScheduleInterval;
                          const defaults = createDefaultScheduleRule(nextInterval);
                          updateRule(idx, {
                            ...defaults,
                            id: rule.id || defaults.id,
                            enabled: rule.enabled !== false,
                          });
                        }}
                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      >
                        {SCHEDULE_INTERVAL_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Rule Enabled
                      </label>
                      <select
                        value={String(rule.enabled !== false)}
                        onChange={(event) => updateRule(idx, { enabled: event.target.value === 'true' })}
                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    </div>
                  </div>

                  {interval === 'custom' && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Cron Expression
                      </label>
                      <input
                        type="text"
                        value={String(rule.cron ?? '')}
                        placeholder="e.g. */15 9-18 * * 1-5"
                        onChange={(event) => updateRule(idx, { cron: event.target.value })}
                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      />
                    </div>
                  )}

                  {interval === 'minutes' && (
                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Minutes Between Triggers
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={59}
                        value={String(rule.every ?? 1)}
                        onChange={(event) => updateRule(idx, { every: event.target.value })}
                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                      />
                    </div>
                  )}

                  {interval === 'hours' && (
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Hours Between Triggers
                        </label>
                        <input
                          type="number"
                          min={1}
                          max={23}
                          value={String(rule.every ?? 1)}
                          onChange={(event) => updateRule(idx, { every: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger At Minute
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={String(rule.trigger_minute ?? 0)}
                          onChange={(event) => updateRule(idx, { trigger_minute: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                    </div>
                  )}

                  {interval === 'days' && (
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Days Between Triggers
                        </label>
                        <input
                          type="number"
                          min={1}
                          max={31}
                          value={String(rule.every ?? 1)}
                          onChange={(event) => updateRule(idx, { every: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Hour
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={23}
                          value={String(rule.trigger_hour ?? 9)}
                          onChange={(event) => updateRule(idx, { trigger_hour: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Minute
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={String(rule.trigger_minute ?? 0)}
                          onChange={(event) => updateRule(idx, { trigger_minute: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                    </div>
                  )}

                  {interval === 'weeks' && (
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Weeks Between Triggers
                        </label>
                        <input
                          type="number"
                          min={1}
                          max={52}
                          value={String(rule.every ?? 1)}
                          onChange={(event) => updateRule(idx, { every: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Weekday
                        </label>
                        <select
                          value={String(rule.trigger_weekday ?? 1)}
                          onChange={(event) => updateRule(idx, { trigger_weekday: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        >
                          {SCHEDULE_WEEKDAY_OPTIONS.map((weekday) => (
                            <option key={weekday.value} value={weekday.value}>
                              {weekday.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Hour
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={23}
                          value={String(rule.trigger_hour ?? 9)}
                          onChange={(event) => updateRule(idx, { trigger_hour: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Minute
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={String(rule.trigger_minute ?? 0)}
                          onChange={(event) => updateRule(idx, { trigger_minute: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                    </div>
                  )}

                  {interval === 'months' && (
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Months Between Triggers
                        </label>
                        <input
                          type="number"
                          min={1}
                          max={12}
                          value={String(rule.every ?? 1)}
                          onChange={(event) => updateRule(idx, { every: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Day Of Month
                        </label>
                        <input
                          type="number"
                          min={1}
                          max={31}
                          value={String(rule.trigger_day_of_month ?? 1)}
                          onChange={(event) => updateRule(idx, { trigger_day_of_month: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Hour
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={23}
                          value={String(rule.trigger_hour ?? 9)}
                          onChange={(event) => updateRule(idx, { trigger_hour: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Trigger Minute
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={String(rule.trigger_minute ?? 0)}
                          onChange={(event) => updateRule(idx, { trigger_minute: event.target.value })}
                          className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            <button
              type="button"
              onClick={() => onChange(field.key, [...normalizedRules, createDefaultScheduleRule('hours')])}
              className="w-full py-2 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 dark:text-slate-600 text-xs font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <Plus size={12} strokeWidth={3} />
              Add Rule
            </button>
          </div>
        );
      }

      case 'array':
        const cases = Array.isArray(value) ? value : [];

        // Auto-migration: Ensure every case has a stable ID
        const casesWithIds = cases.map((c: any, idx: number) => {
          const stableId = normalizeSwitchCaseId(c, idx);
          if (String(c?.id || '').trim() !== stableId) {
            return { ...c, id: stableId };
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
                    {SWITCH_CASE_OPERATORS.map((op) => (
                      <option key={op} value={op}>{op}</option>
                    ))}
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

      case 'sheet_update_mappings': {
        const rawMappings = Array.isArray(value) ? value : [];
        const legacyColumn = String(config.update_column || '').trim();
        const legacyValue = config.update_value ?? '';

        const initialMappings = rawMappings.length > 0
          ? rawMappings
          : (legacyColumn
            ? [{ id: `mapping_${Date.now()}`, column: legacyColumn, value: legacyValue }]
            : []);

        const normalizedMappings = initialMappings.map((item: any, idx: number) => ({
          id: String(item?.id || `mapping_${idx}_${Math.random().toString(36).slice(2, 7)}`),
          column: String(item?.column || item?.update_column || '').trim(),
          value: item?.value ?? item?.update_value ?? '',
        }));

        if (JSON.stringify(rawMappings) !== JSON.stringify(normalizedMappings)) {
          onChange(field.key, normalizedMappings);
        }

        const updateMapping = (index: number, patch: Record<string, any>) => {
          const next = [...normalizedMappings];
          next[index] = { ...next[index], ...patch };
          onChange(field.key, next);
        };

        return (
          <div className="space-y-3">
            {normalizedMappings.map((mapping: any, idx: number) => (
              <div key={mapping.id || idx} className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl space-y-2 relative group transition-colors">
                <button
                  onClick={() => {
                    const next = [...normalizedMappings];
                    next.splice(idx, 1);
                    onChange(field.key, next);
                  }}
                  className="absolute top-2 right-2 text-slate-300 dark:text-slate-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
                <input
                  type="text"
                  placeholder="Column (e.g. Status, D, 4)"
                  value={mapping.column || ''}
                  onChange={(e) => updateMapping(idx, { column: e.target.value })}
                  className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500 dark:focus:border-blue-400 placeholder:text-slate-300 dark:placeholder:text-slate-700 transition-all"
                />
                <div className="relative">
                  <input
                    type="text"
                    placeholder={dragOverField === `${field.key}_${idx}` ? 'Drop to insert…' : 'Value (supports {{...}})'}
                    value={String(mapping.value ?? '')}
                    onChange={(e) => updateMapping(idx, { value: e.target.value })}
                    onDragOver={(e) => handleDragOver(e, `${field.key}_${idx}`)}
                    onDragLeave={(e) => handleDragLeave(e)}
                    onDrop={(e) => handleArrayDrop(e, field.key, normalizedMappings, idx, 'value')}
                    className={`w-full bg-white dark:bg-slate-900 border rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none transition-all placeholder:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === `${field.key}_${idx}`
                      ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                      : 'border-slate-200 dark:border-slate-700 focus:border-blue-500 dark:focus:border-blue-400'
                      }`}
                  />
                </div>
              </div>
            ))}
            <button
              onClick={() => onChange(field.key, [...normalizedMappings, { id: `mapping_${Date.now()}`, column: '', value: '' }])}
              className="w-full py-2 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 dark:text-slate-600 text-xs font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <Plus size={12} strokeWidth={3} />
              Add Column Mapping
            </button>
          </div>
        );
      }

      case 'credential_selector':
        const filteredCreds = credentials.filter(c => c.app_name === field.appName);
        const credentialFormId = `${field.appName}:${field.key}`;
        const requiresChatId = Boolean(field.requiresChatId);
        const requiresPhoneNumberId = Boolean(field.requiresPhoneNumberId);
        const requiresChannel = Boolean(field.requiresChannel);
        const normalizedAppName = String(field.appName || '').toLowerCase();
        const isOAuthOnlyApp = OAUTH_APPS.includes(normalizedAppName as (typeof OAUTH_APPS)[number]);
        const oauthAppLabel = OAUTH_APP_LABEL[normalizedAppName] || 'OAuth';
        const oauthNodeUsage = OAUTH_NODE_USAGE[normalizedAppName] || [];
        const secretValue = newKey;
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
                  <option key={c.id} value={c.id}>
                    {(c.display_name || c.app_name)} - {c.id.substring(0, 8)}...
                  </option>
                ))}
              </select>
              {!isOAuthOnlyApp && (
                <button
                  onClick={() => {
                    void fetchCredentials();
                    setNewKey('');
                    setNewChatId('');
                    setNewPhoneNumberId('');
                    setNewChannel('');
                    setActiveCredentialForm((current) => (
                      current === credentialFormId ? null : credentialFormId
                    ));
                  }}
                  className="px-3 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5v14" /></svg>
                </button>
              )}
            </div>
            {isOAuthOnlyApp && (
              <>
                <button
                  type="button"
                  onClick={() => void handleQuickGoogleOAuthConnect(normalizedAppName)}
                  disabled={oauthConnectingApp === normalizedAppName}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-60"
                >
                  <GoogleMark className="h-4 w-4" />
                  {oauthConnectingApp === normalizedAppName ? 'Connecting...' : `Connect ${oauthAppLabel} OAuth`}
                </button>
                <p className="text-[11px] text-slate-500 dark:text-[11px] dark:text-slate-400">
                  OAuth only. Use the button above for quick verification, then select the credential.
                </p>
                {oauthNodeUsage.length > 0 && (
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Used by: {oauthNodeUsage.join(', ')}
                  </p>
                )}
              </>
            )}
            {!isOAuthOnlyApp && activeCredentialForm === credentialFormId && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-xl space-y-2 animate-in fade-in slide-in-from-top-2 duration-200">
                <label className="text-[9px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                  Add {field.appName} {field.credentialLabel || 'API Key'}
                </label>
                <div className="space-y-2">
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
                  {requiresChannel && (
                    <input
                      type="text"
                      name={`credential-channel-${credentialFormId}`}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="Slack Channel (e.g. #general or @username)"
                      value={newChannel}
                      onChange={(e) => setNewChannel(e.target.value)}
                      className="w-full bg-white dark:bg-slate-900 border border-blue-200 dark:border-blue-800 rounded-lg px-2 py-1.5 text-xs text-slate-700 dark:text-slate-300 outline-none focus:border-blue-500"
                    />
                  )}
                  <button
                    disabled={loading || !secretValue.trim() || (requiresChatId && !newChatId.trim()) || (requiresPhoneNumberId && !newPhoneNumberId.trim()) || (requiresChannel && !newChannel.trim())}
                    onClick={() => {
                      const extraData: Record<string, string> = {};
                                      if (requiresChatId) {
                        extraData.chat_id = newChatId.trim();
                      }
                      if (requiresPhoneNumberId) {
                        extraData.phone_number_id = newPhoneNumberId.trim();
                      }
                      if (requiresChannel) {
                        extraData.channel = newChannel.trim();
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
        const isPathPlaceholderForTextarea = PATH_STYLE_FIELD_KEYS.has(field.key);
        return (
          <div className="relative">
            <textarea
              value={value}
              placeholder={dragOverField === field.key ? (isPathPlaceholderForTextarea ? 'Drop to insert path…' : 'Drop to insert {{path}}…') : field.placeholder}
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
        const isPathPlaceholderForText = PATH_STYLE_FIELD_KEYS.has(field.key);
        return (
          <div className="relative">
            <input
              type="text"
              value={value}
              placeholder={dragOverField === field.key ? (isPathPlaceholderForText ? 'Drop to insert path…' : 'Drop to insert {{path}}…') : field.placeholder}
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

  const shouldRenderField = (field: any): boolean => {
    if (nodeType !== 'search_update_google_sheets') {
      return true;
    }

    const sourceType = String(config.spreadsheet_source_type || 'id').trim().toLowerCase();
    const operation = normalizeSheetsOperation(config.operation, Boolean(config.upsert_if_not_found));

    if (field.key === 'spreadsheet_id') return sourceType !== 'url';
    if (field.key === 'spreadsheet_url') return sourceType === 'url';

    if (field.key === 'key_column' || field.key === 'key_value') {
      return ['delete_rows', 'overwrite_row', 'upsert_row'].includes(operation);
    }
    if (field.key === 'append_columns' || field.key === 'append_values') {
      return false;
    }
    if (field.key === 'update_mappings') {
      return ['append_row', 'overwrite_row', 'upsert_row'].includes(operation);
    }
    if (field.key === 'columns_to_add') {
      return operation === 'add_columns';
    }
    if (field.key === 'columns_to_delete') {
      return operation === 'delete_columns';
    }
    if (field.key === 'auto_create_headers') {
      return ['append_row', 'overwrite_row', 'upsert_row', 'add_columns'].includes(operation);
    }

    return true;
  };

  return (
    <div className="space-y-6">
      {fields.length === 0 ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 dark:text-slate-700 gap-3">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="opacity-20"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" /><polyline points="14 2 14 8 20 8" /></svg>
          <span className="text-sm font-medium">No configuration available for this node type.</span>
        </div>
      ) : (
        fields.filter((field) => shouldRenderField(field)).map((field) => (
          <div key={field.key} className="space-y-2">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-600 flex items-center justify-between">
              {field.label}
              {(field.type === 'text' || field.type === 'textarea' || field.type === 'sheet_update_mappings' || field.type === 'string_array') && (
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
