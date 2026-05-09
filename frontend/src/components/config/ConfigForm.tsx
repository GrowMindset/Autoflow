import React, { useCallback, useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Plus } from 'lucide-react';
import { CredentialItem, credentialService } from '../../services/credentialService';
import { getAppTimezone } from '../../utils/dateTime';
import { WorkflowNode } from '../../types/workflow';

const OAUTH_APPS = ['gmail', 'sheets', 'docs', 'linkedin'] as const;
const OAUTH_NODE_USAGE: Record<string, string[]> = {
  gmail: ['Get Gmail Message', 'Send Gmail Message'],
  sheets: ['Create Google Sheets', 'Read Google Sheets', 'Search/Update Google Sheets'],
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

const FILTER_DATA_TYPE_OPTIONS = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'date', label: 'Date & Time' },
  { value: 'array', label: 'Array' },
  { value: 'object', label: 'Object' },
] as const;

const FILTER_OPERATORS_BY_DATA_TYPE: Record<string, string[]> = {
  string: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'equals',
    'not_equals',
    'contains',
    'not_contains',
    'starts_with',
    'does_not_start_with',
    'ends_with',
    'does_not_end_with',
    'matches_regex',
    'does_not_match_regex',
  ],
  number: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'equals',
    'not_equals',
    'greater_than',
    'less_than',
    'greater_than_or_equals',
    'less_than_or_equals',
  ],
  boolean: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'is_true',
    'is_false',
    'equals',
    'not_equals',
  ],
  date: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'equals',
    'not_equals',
    'after',
    'before',
    'after_or_equal',
    'before_or_equal',
  ],
  array: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'contains',
    'not_contains',
    'length_equals',
    'length_not_equals',
    'length_greater_than',
    'length_less_than',
    'length_greater_than_or_equals',
    'length_less_than_or_equals',
  ],
  object: [
    'exists',
    'does_not_exist',
    'is_empty',
    'is_not_empty',
    'equals',
    'not_equals',
  ],
};

const FILTER_OPERATOR_LABELS: Record<string, string> = {
  exists: 'exists',
  does_not_exist: 'does not exist',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
  equals: 'equals',
  not_equals: 'not equals',
  contains: 'contains',
  not_contains: 'does not contain',
  starts_with: 'starts with',
  does_not_start_with: 'does not start with',
  ends_with: 'ends with',
  does_not_end_with: 'does not end with',
  matches_regex: 'matches regex',
  does_not_match_regex: 'does not match regex',
  greater_than: 'greater than',
  less_than: 'less than',
  greater_than_or_equals: 'greater than or equals',
  less_than_or_equals: 'less than or equals',
  is_true: 'is true',
  is_false: 'is false',
  after: 'is after',
  before: 'is before',
  after_or_equal: 'is after or equal',
  before_or_equal: 'is before or equal',
  length_equals: 'length equals',
  length_not_equals: 'length not equals',
  length_greater_than: 'length greater than',
  length_less_than: 'length less than',
  length_greater_than_or_equals: 'length greater than or equals',
  length_less_than_or_equals: 'length less than or equals',
};

const FILTER_OPERATORS_WITHOUT_COMPARE_INPUT = new Set([
  'exists',
  'does_not_exist',
  'is_empty',
  'is_not_empty',
  'is_true',
  'is_false',
]);

const FILTER_STRING_OPERATORS = new Set([
  'equals',
  'not_equals',
  'contains',
  'not_contains',
  'starts_with',
  'does_not_start_with',
  'ends_with',
  'does_not_end_with',
  'matches_regex',
  'does_not_match_regex',
]);

const getDroppedPathValue = (path: string, fieldKey: string): string =>
  PATH_STYLE_FIELD_KEYS.has(fieldKey) ? path : `{{${path}}}`;

const normalizeSwitchCaseId = (rawCase: any, index: number): string => {
  const explicitId = String(rawCase?.id || '').trim();
  if (explicitId) return explicitId;
  const labelBased = String(rawCase?.label || '').trim();
  if (labelBased) return labelBased;
  return `case_${index + 1}`;
};

const normalizeFilterConditionId = (rawCondition: any, index: number): string => {
  const explicitId = String(rawCondition?.id || '').trim();
  if (explicitId) return explicitId;
  return `condition_${index + 1}`;
};

const normalizeFilterCondition = (
  rawCondition: any,
  index: number,
  fallbackJoin: 'and' | 'or' = 'and',
) => {
  const rawObject = rawCondition && typeof rawCondition === 'object' ? rawCondition : {};
  const dataTypeRaw = String(rawObject.data_type || '').trim().toLowerCase();
  const dataType = FILTER_DATA_TYPE_OPTIONS.some((option) => option.value === dataTypeRaw)
    ? dataTypeRaw
    : 'string';
  const allowedOperators = FILTER_OPERATORS_BY_DATA_TYPE[dataType] || FILTER_OPERATORS_BY_DATA_TYPE.string;
  const valueModeRaw = String(rawObject.value_mode || 'literal').trim().toLowerCase();
  const valueMode = valueModeRaw === 'field' ? 'field' : 'literal';
  const caseSensitiveRaw = rawObject.case_sensitive;

  let caseSensitive = true;
  if (typeof caseSensitiveRaw === 'boolean') {
    caseSensitive = caseSensitiveRaw;
  } else if (typeof caseSensitiveRaw === 'number') {
    caseSensitive = caseSensitiveRaw !== 0;
  } else if (typeof caseSensitiveRaw === 'string') {
    const normalized = caseSensitiveRaw.trim().toLowerCase();
    if (['0', 'false', 'no', 'off'].includes(normalized)) {
      caseSensitive = false;
    }
  }

  const operatorRaw = String(rawObject.operator || 'equals').trim().toLowerCase();
  const operator = allowedOperators.includes(operatorRaw) ? operatorRaw : (allowedOperators[0] || 'equals');
  const joinRaw = String(
    rawObject.join_with_previous
    || rawObject.condition
    || rawObject.logic
    || fallbackJoin,
  ).trim().toLowerCase();
  const joinWithPrevious = joinRaw === 'or' ? 'or' : 'and';

  return {
    id: normalizeFilterConditionId(rawObject, index),
    field: String(rawObject.field || ''),
    operator,
    data_type: dataType,
    value_mode: valueMode,
    value_field: String(rawObject.value_field || ''),
    value: valueMode === 'field' ? '' : String(rawObject.value ?? ''),
    case_sensitive: caseSensitive,
    join_with_previous: index === 0 ? 'and' : joinWithPrevious,
  };
};

type FilterCondition = ReturnType<typeof normalizeFilterCondition>;
type FilterConditionDropKey = Extract<keyof FilterCondition, 'field' | 'value_field' | 'value'>;

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
    {
      key: 'conditions',
      label: 'Conditions',
      type: 'filter_conditions',
      helperText: 'Add one or more condition rows. Supports field-to-field comparisons.',
    },
  ],
  limit: [
    { key: 'input_key', label: 'Input Array Key', type: 'text', placeholder: 'e.g. items' },
    { key: 'limit', label: 'Limit', type: 'text', placeholder: 'e.g. 10' },
    { key: 'offset', label: 'Offset', type: 'text', placeholder: 'e.g. 0' },
    {
      key: 'start_from',
      label: 'Start From',
      type: 'select',
      options: ['start', 'end'],
      helperText: "start = from first item, end = from last item.",
    },
  ],
  sort: [
    { key: 'input_key', label: 'Input Array Key', type: 'text', placeholder: 'e.g. items' },
    {
      key: 'sort_by',
      label: 'Sort Field (Optional)',
      type: 'text',
      placeholder: 'e.g. amount or user.created_at',
      helperText: 'Leave empty to sort primitive arrays directly.',
    },
    {
      key: 'order',
      label: 'Order',
      type: 'select',
      options: ['asc', 'desc'],
    },
    {
      key: 'data_type',
      label: 'Data Type',
      type: 'select',
      options: ['auto', 'string', 'number', 'boolean', 'date'],
    },
    {
      key: 'nulls',
      label: 'Null / Missing Values',
      type: 'select',
      options: ['last', 'first'],
    },
    { key: 'case_sensitive', label: 'Case Sensitive (strings)', type: 'boolean' },
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
  merge: [
    {
      key: 'input_count',
      label: 'Number of Inputs',
      type: 'select',
      options: ['2', '3', '4', '5', '6'],
      helperText: 'How many merge input handles to expose on the node.',
    },
    {
      key: 'mode',
      label: 'Merge Mode',
      type: 'select',
      options: ['append', 'combine', 'combine_by_position', 'combine_by_fields', 'choose_branch'],
      helperText: 'n8n-style merge: append, combine, or choose_branch.',
    },
    {
      key: 'choose_branch',
      label: 'Choose Branch',
      type: 'merge_branch_selector',
      helperText: 'Used when mode = choose_branch.',
    },
    {
      key: 'join_type',
      label: 'Join Type',
      type: 'select',
      options: ['inner', 'left', 'right', 'outer'],
      helperText: 'Used by combine_by_position and combine_by_fields.',
    },
    {
      key: 'input_1_field',
      label: 'Input 1 Match Field',
      type: 'text',
      placeholder: 'e.g. email or user.id',
      helperText: 'Used by combine_by_fields.',
    },
    {
      key: 'input_2_field',
      label: 'Input 2 Match Field',
      type: 'text',
      placeholder: 'e.g. email or profile.id',
      helperText: 'Used by combine_by_fields.',
    },
    {
      key: 'output_key',
      label: 'Output Key',
      type: 'text',
      placeholder: 'merged',
      helperText: 'Used by append/combine modes that return arrays.',
    },
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
    { key: 'input_data_mode', label: 'Input Data Mode', type: 'select', options: ['fields', 'json_example', 'accept_all'] }
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
    {
      key: 'image',
      label: 'Image',
      type: 'textarea',
      placeholder: 'e.g. {{image_gen_1.image_base64}} or {{image_gen_1.image_url}}',
      helperText: 'Optional. Supports Image Gen base64 or data URI output.',
      imageTemplateHints: true,
    },
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
  read_google_sheets: [
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
      key: 'range',
      label: 'Range (Optional)',
      type: 'text',
      placeholder: 'e.g. A1:F200 or Sheet1!A:Z',
      helperText: 'Leave empty to read the full sheet range (A:ZZ).',
    },
    { key: 'first_row_as_header', label: 'Use First Row As Header', type: 'boolean' },
    { key: 'include_empty_rows', label: 'Include Empty Rows', type: 'boolean' },
    { key: 'max_rows', label: 'Max Rows (Optional)', type: 'text', placeholder: 'e.g. 1000' },
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
  read_google_docs: [
    {
      key: 'credential_id',
      label: 'Google Docs Credential',
      type: 'credential_selector',
      appName: 'docs',
      helperText: 'OAuth only: connect Google Docs in Credential Manager, then select it here.',
    },
    {
      key: 'document_source_type',
      label: 'Document Source',
      type: 'select',
      options: ['id', 'url'],
    },
    { key: 'document_id', label: 'Document ID', type: 'text', placeholder: 'e.g. 1AbCdEf...' },
    {
      key: 'document_url',
      label: 'Document URL',
      type: 'text',
      placeholder: 'https://docs.google.com/document/d/.../edit',
      helperText: "Required when Document Source is 'url'.",
    },
    { key: 'max_characters', label: 'Max Characters (Optional)', type: 'text', placeholder: 'e.g. 5000' },
    { key: 'include_raw_json', label: 'Include Raw Google Response', type: 'boolean' },
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
    {
      key: 'image',
      label: 'Image',
      type: 'textarea',
      placeholder: 'e.g. {{image_gen_1.image_url}}',
      helperText: 'Optional. Google Docs insertInlineImage expects a retrievable URI; Image Gen data URI support may depend on Google API acceptance.',
      imageTemplateHints: true,
    },
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
    {
      key: 'image',
      label: 'Image',
      type: 'textarea',
      placeholder: 'e.g. {{image_gen_1.image_base64}} or {{image_gen_1.image_url}}',
      helperText: 'Optional. If set, Telegram sends a photo and uses Message Text as the caption.',
      imageTemplateHints: true,
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
      key: 'image',
      label: 'Image',
      type: 'textarea',
      placeholder: 'e.g. {{image_gen_1.image_base64}} or {{image_gen_1.image_url}}',
      helperText: 'Optional. Uploads the image to LinkedIn before publishing the post.',
      imageTemplateHints: true,
    },
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
  image_gen: [
    { key: 'credential_id', label: 'Credential', type: 'credential_selector', appName: 'openai' },
    {
      key: 'model',
      label: 'Model',
      type: 'select',
      options: ['gpt-image-1', 'dall-e-3', 'dall-e-2'],
    },
    {
      key: 'prompt',
      label: 'Image Prompt',
      type: 'textarea',
      placeholder: 'Describe the image you want to generate...',
      helperText: 'Template syntax: {{previous_node_id.field}}',
    },
    {
      key: 'size',
      label: 'Size',
      type: 'select',
      dynamicOptionsBy: 'model',
      optionsByProvider: {
        'dall-e-3': ['1024x1024', '1792x1024', '1024x1792'],
        'dall-e-2': ['256x256', '512x512', '1024x1024'],
        'gpt-image-1': ['1024x1024', '1536x1024', '1024x1536'],
      },
      options: ['1024x1024'],
    },
    {
      key: 'quality',
      label: 'Quality',
      type: 'select',
      options: ['standard', 'hd'],
    },
    {
      key: 'style',
      label: 'Style',
      type: 'select',
      options: ['vivid', 'natural'],
    },
  ],
  chat_model_openai: [
    { key: 'credential_id', label: 'Credential', type: 'credential_selector', appName: 'openai' },
    {
      key: 'model',
      label: 'Model',
      type: 'select',
      options: ['gpt-5.5','gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano']
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
  previousNodes?: WorkflowNode[];
  onChange: (key: string, value: any) => void;
  onChangePatch?: (patch: Record<string, any>) => void;
}

const ConfigForm: React.FC<ConfigFormProps> = ({
  nodeType,
  config,
  previousNodes = [],
  onChange,
  onChangePatch,
}) => {
  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeCredentialForm, setActiveCredentialForm] = useState<string | null>(null);
  const [newKey, setNewKey] = useState('');
  const [newChatId, setNewChatId] = useState('');
  const [newPhoneNumberId, setNewPhoneNumberId] = useState('');
  const [newChannel, setNewChannel] = useState('');
  const [dragOverField, setDragOverField] = useState<string | null>(null);
  const [oauthConnectingApp, setOauthConnectingApp] = useState<string | null>(null);

  const applyConfigPatch = useCallback((patch: Record<string, any>) => {
    const safePatch = patch || {};
    if (onChangePatch) {
      onChangePatch(safePatch);
      return;
    }
    Object.entries(safePatch).forEach(([key, value]) => {
      onChange(key, value);
    });
  }, [onChange, onChangePatch]);

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

  const resolveDropInsertText = ({
    fieldKey,
    dataTransfer,
  }: {
    fieldKey: string;
    dataTransfer: DataTransfer;
  }): string => {
    const literalValue = dataTransfer.getData('application/json-value');
    if (literalValue) {
      return literalValue;
    }

    const path = dataTransfer.getData('application/json-path');
    if (path) {
      return getDroppedPathValue(path, fieldKey);
    }

    return dataTransfer.getData('text/plain') || '';
  };

  const handleDrop = (e: React.DragEvent, fieldKey: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverField(null);

    const textToInsert = resolveDropInsertText({
      fieldKey,
      dataTransfer: e.dataTransfer,
    });
    if (!textToInsert) return;

    const el = e.currentTarget as HTMLInputElement | HTMLTextAreaElement;
    const current = String(config[fieldKey] ?? '');
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? start;
    const nextValue = current.slice(0, start) + textToInsert + current.slice(end);
    onChange(fieldKey, nextValue);
  };

  const handleArrayDrop = (
    e: React.DragEvent,
    fieldKey: string,
    arrayRef: any[],
    index: number,
    itemKey?: string,
  ) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverField(null);

    const textToInsert = resolveDropInsertText({
      fieldKey,
      dataTransfer: e.dataTransfer,
    });
    if (!textToInsert) return;

    const el = e.currentTarget as HTMLInputElement;
    const current = itemKey
      ? String(arrayRef[index]?.[itemKey] || '')
      : String(arrayRef[index] || '');
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? start;

    const next = [...arrayRef];
    if (itemKey) {
      next[index] = {
        ...(next[index] || {}),
        [itemKey]: current.slice(0, start) + textToInsert + current.slice(end),
      };
    } else {
      next[index] = current.slice(0, start) + textToInsert + current.slice(end);
    }

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

    if (Object.keys(patch).length > 0) {
      applyConfigPatch(patch);
    }
  }, [nodeType, config, applyConfigPatch]);

  useEffect(() => {
    if (nodeType !== 'read_google_sheets') return;

    const patch: Record<string, any> = {};
    const sourceTypeRaw = String(config.spreadsheet_source_type || '').trim().toLowerCase();
    if (!sourceTypeRaw) {
      patch.spreadsheet_source_type = String(config.spreadsheet_url || '').trim() ? 'url' : 'id';
    }
    if (typeof config.sheet_name === 'undefined') {
      patch.sheet_name = 'Sheet1';
    }
    if (typeof config.first_row_as_header === 'undefined') {
      patch.first_row_as_header = true;
    }
    if (typeof config.include_empty_rows === 'undefined') {
      patch.include_empty_rows = false;
    }

    if (Object.keys(patch).length > 0) {
      applyConfigPatch(patch);
    }
  }, [nodeType, config, applyConfigPatch]);

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

    if (Object.keys(patch).length > 0) {
      applyConfigPatch(patch);
    }
  }, [
    nodeType,
    config,
    applyConfigPatch,
  ]);

  useEffect(() => {
    if (nodeType !== 'image_gen') return;

    const sizesByModel: Record<string, string[]> = {
      'dall-e-3': ['1024x1024', '1792x1024', '1024x1792'],
      'dall-e-2': ['256x256', '512x512', '1024x1024'],
      'gpt-image-1': ['1024x1024', '1536x1024', '1024x1536'],
    };
    const model = String(config.model || 'dall-e-3');
    const allowedSizes = sizesByModel[model] || sizesByModel['dall-e-3'];
    if (!allowedSizes.includes(String(config.size || ''))) {
      applyConfigPatch({ size: allowedSizes[0] });
    }
  }, [nodeType, config.model, config.size, applyConfigPatch]);

  useEffect(() => {
    if (nodeType !== 'merge') return;

    const mode = String(config.mode || '').trim().toLowerCase();
    const normalizedMode = mode === 'choose_input_1' || mode === 'choose_input1'
      ? 'choose_branch'
      : mode === 'choose_input_2' || mode === 'choose_input2'
        ? 'choose_branch'
        : mode;
    const rawInputCount = Number.parseInt(String(config.input_count ?? ''), 10);
    const normalizedInputCount = Number.isFinite(rawInputCount)
      ? Math.min(6, Math.max(2, rawInputCount))
      : 2;
    const chooseBranchValue = String(config.choose_branch || '').trim().toLowerCase();
    const normalizedChooseBranch = !chooseBranchValue
      ? (mode === 'choose_input_2' || mode === 'choose_input2' ? 'input2' : 'input1')
      : chooseBranchValue;

    const patch: Record<string, any> = {};
    if (!mode) {
      patch.mode = 'append';
    } else if (normalizedMode !== mode) {
      patch.mode = normalizedMode;
    }
    if (String(config.input_count || '') !== String(normalizedInputCount)) {
      patch.input_count = normalizedInputCount;
    }
    if (normalizedChooseBranch !== chooseBranchValue) {
      patch.choose_branch = normalizedChooseBranch;
    }
    if (Object.keys(patch).length > 0) {
      applyConfigPatch(patch);
    }
  }, [nodeType, config, applyConfigPatch]);

  const fields = CONFIG_SCHEMA[nodeType] || [];

  const imageTemplateHints = previousNodes
    .filter((previousNode) => previousNode.data?.type === 'image_gen')
    .flatMap((previousNode) => [
      `{{${previousNode.id}.image_base64}}`,
      `{{${previousNode.id}.image_url}}`,
    ]);

  const getModeAwareFieldValue = (field: any, fallbackValue: any): any => {
    if (!field?.key) return fallbackValue;
    return typeof config[field.key] === 'undefined' ? fallbackValue : config[field.key];
  };

  const handleModeAwareFieldChange = (field: any, nextValue: any) => {
    const fieldKey = String(field.key || '').trim();
    if (!fieldKey) return;
    onChange(fieldKey, nextValue);
  };

  const getModeAwareTextValue = (field: any): any =>
    getModeAwareFieldValue(field, config[field.key] ?? '');

  const handleModeAwareTextChange = (field: any, nextValue: any) => {
    handleModeAwareFieldChange(field, nextValue);
  };

  const toBooleanLike = (rawValue: any): boolean => {
    if (typeof rawValue === 'boolean') return rawValue;
    if (typeof rawValue === 'number') return rawValue !== 0;
    if (typeof rawValue === 'string') {
      const normalized = rawValue.trim().toLowerCase();
      return ['1', 'true', 'yes', 'on'].includes(normalized);
    }
    return false;
  };

  const insertImageHint = (fieldKey: string, hint: string) => {
    const current = String(config[fieldKey] || '');
    const separator = current && !current.endsWith('\n') ? '\n' : '';
    onChange(fieldKey, `${current}${separator}${hint}`);
  };



  const renderField = (field: any) => {
    const value = config[field.key] ?? '';

    switch (field.type) {
      case 'select': {
        const selectOptions = field.dynamicOptionsBy
          ? (field.optionsByProvider?.[config[field.dynamicOptionsBy] || 'openai'] || [])
          : field.options;
        const selectValue = getModeAwareFieldValue(field, value);

        return (
          <select
            value={String(selectValue ?? '')}
            onChange={(e) => handleModeAwareFieldChange(field, e.target.value)}
            className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
          >
            <option value="">Select option...</option>
            {selectOptions.map((opt: string) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );
      }

      case 'merge_branch_selector': {
        const rawInputCount = Number.parseInt(String(config.input_count ?? ''), 10);
        const inputCount = Number.isFinite(rawInputCount)
          ? Math.min(6, Math.max(2, rawInputCount))
          : 2;
        const options = Array.from({ length: inputCount }, (_, idx) => `input${idx + 1}`);
        const selectedBranch = String(value || options[0] || 'input1');

        return (
          <select
            value={selectedBranch}
            onChange={(e) => onChange(field.key, e.target.value)}
            className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
          >
            {options.map((opt) => (
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
        const boolValue = toBooleanLike(getModeAwareFieldValue(field, value));
        return (
          <select
            value={String(boolValue)}
            onChange={(e) => handleModeAwareFieldChange(field, e.target.value === 'true')}
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

      case 'filter_conditions': {
        const fallbackJoin: 'and' | 'or' = String(config.logic || '').trim().toLowerCase() === 'or'
          ? 'or'
          : 'and';
        const rawConditions = Array.isArray(value) ? value : [];
        const normalizedConditions = (rawConditions.length > 0 ? rawConditions : [{}]).map(
          (condition: any, idx: number) => normalizeFilterCondition(condition, idx, fallbackJoin),
        );

        if (JSON.stringify(rawConditions) !== JSON.stringify(normalizedConditions)) {
          onChange(field.key, normalizedConditions);
        }

        const updateCondition = (index: number, patch: Record<string, any>) => {
          const next = [...normalizedConditions];
          const existing = next[index] || normalizeFilterCondition({}, index, fallbackJoin);
          const updated = { ...existing, ...patch };
          if (typeof patch.data_type === 'string') {
            const nextDataType = String(patch.data_type).trim().toLowerCase();
            const nextOperators = FILTER_OPERATORS_BY_DATA_TYPE[nextDataType] || FILTER_OPERATORS_BY_DATA_TYPE.string;
            if (!nextOperators.includes(String(updated.operator || ''))) {
              updated.operator = nextOperators[0] || 'equals';
            }
          }
          const operatorForUpdated = String(updated.operator || '').trim().toLowerCase();
          if (FILTER_OPERATORS_WITHOUT_COMPARE_INPUT.has(operatorForUpdated)) {
            updated.value_mode = 'literal';
            updated.value = '';
            updated.value_field = '';
          }
          if (updated.value_mode === 'field') {
            updated.value = '';
          }
          next[index] = normalizeFilterCondition(updated, index, fallbackJoin);
          onChange(field.key, next);
        };

        const removeCondition = (index: number) => {
          const next = [...normalizedConditions];
          next.splice(index, 1);
          onChange(field.key, next.length > 0 ? next : [normalizeFilterCondition({}, 0, fallbackJoin)]);
        };

        const addCondition = () => {
          const nextIndex = normalizedConditions.length;
          const defaultJoin = nextIndex === 0
            ? 'and'
            : String(normalizedConditions[nextIndex - 1]?.join_with_previous || fallbackJoin) === 'or'
              ? 'or'
              : 'and';
          const next = [
            ...normalizedConditions,
            normalizeFilterCondition(
              {
                id: `condition_${Math.random().toString(36).slice(2, 9)}`,
                operator: 'equals',
                value_mode: 'literal',
                case_sensitive: true,
                join_with_previous: defaultJoin,
              },
              nextIndex,
              fallbackJoin,
            ),
          ];
          onChange(field.key, next);
        };

        const handleFilterConditionDrop = (
          event: React.DragEvent<HTMLInputElement>,
          index: number,
          conditionKey: FilterConditionDropKey,
          dropFieldKey: string,
        ) => {
          event.preventDefault();
          event.stopPropagation();
          setDragOverField(null);

          const textToInsert = resolveDropInsertText({
            fieldKey: dropFieldKey,
            dataTransfer: event.dataTransfer,
          });
          if (!textToInsert) return;

          const el = event.currentTarget;
          const current = String(normalizedConditions[index]?.[conditionKey] ?? '');
          const start = el.selectionStart ?? current.length;
          const end = el.selectionEnd ?? start;
          const nextValue = current.slice(0, start) + textToInsert + current.slice(end);
          updateCondition(index, { [conditionKey]: nextValue });
        };

        return (
          <div className="space-y-3">
            {normalizedConditions.map((condition: any, idx: number) => {
              const dataType = String(condition.data_type || 'string').toLowerCase();
              const availableOperators = FILTER_OPERATORS_BY_DATA_TYPE[dataType] || FILTER_OPERATORS_BY_DATA_TYPE.string;
              const operator = String(condition.operator || 'equals');
              const valueMode = String(condition.value_mode || 'literal') === 'field'
                ? 'field'
                : 'literal';
              const requiresCompareValue = !FILTER_OPERATORS_WITHOUT_COMPARE_INPUT.has(operator);
              const joinWithPrevious = String(condition.join_with_previous || 'and') === 'or' ? 'or' : 'and';
              const caseSensitive = Boolean(condition.case_sensitive ?? true);
              const usesStringComparison = dataType === 'string' && FILTER_STRING_OPERATORS.has(operator);
              const fieldDropKey = `filter_condition_field_${idx}`;
              const valueFieldDropKey = `filter_condition_value_field_${idx}`;
              const valueDropKey = `filter_condition_value_${idx}`;

              return (
                <div key={condition.id || idx} className="space-y-2.5">
                  {idx > 0 && normalizedConditions.length > 1 && (
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Join with previous
                      </span>
                      <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
                        {(['and', 'or'] as const).map((joinOption) => (
                          <button
                            key={joinOption}
                            type="button"
                            onClick={() => updateCondition(idx, { join_with_previous: joinOption })}
                            className={`rounded-md px-2.5 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${
                              joinWithPrevious === joinOption
                                ? 'bg-blue-600 text-white'
                                : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                            }`}
                          >
                            {joinOption}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="relative space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
                    <button
                      type="button"
                      onClick={() => removeCondition(idx)}
                      className="absolute right-2 top-2 text-slate-300 transition-colors hover:text-red-500 dark:text-slate-700 dark:hover:text-red-400"
                      title="Remove condition"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                    </button>

                    <div className="pr-8 text-[11px] font-bold text-slate-600 dark:text-slate-300">
                      Condition {idx + 1}
                    </div>

                    <div className="space-y-1">
                      <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Left Field Path
                      </label>
                      <input
                        type="text"
                        value={String(condition.field || '')}
                        placeholder={dragOverField === fieldDropKey ? 'Drop to insert path…' : 'e.g. amount or user.status'}
                        onChange={(event) => updateCondition(idx, { field: event.target.value })}
                        onDragOver={(event) => handleDragOver(event, fieldDropKey)}
                        onDragLeave={(event) => handleDragLeave(event)}
                        onDrop={(event) => handleFilterConditionDrop(event, idx, 'field', 'field')}
                        className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === fieldDropKey
                          ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                          : 'border-slate-200 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                          }`}
                      />
                    </div>

                    <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Data Type
                        </label>
                        <select
                          value={dataType}
                          onChange={(event) => updateCondition(idx, { data_type: event.target.value })}
                          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:focus:border-blue-400"
                        >
                          {FILTER_DATA_TYPE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Operator
                        </label>
                        <select
                          value={operator}
                          onChange={(event) => updateCondition(idx, { operator: event.target.value })}
                          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:focus:border-blue-400"
                        >
                          {availableOperators.map((op) => (
                            <option key={op} value={op}>{FILTER_OPERATOR_LABELS[op] || op}</option>
                          ))}
                        </select>
                      </div>

                      {requiresCompareValue ? (
                        <div className="space-y-1">
                          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            Compare With
                          </label>
                          <select
                            value={valueMode}
                            onChange={(event) => updateCondition(idx, { value_mode: event.target.value })}
                            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:focus:border-blue-400"
                          >
                            <option value="literal">Literal Value</option>
                            <option value="field">Another Field</option>
                          </select>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                            Compare With
                          </label>
                          <div className="w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                            Not required
                          </div>
                        </div>
                      )}
                    </div>

                    {requiresCompareValue && valueMode === 'field' ? (
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Right Field Path
                        </label>
                        <input
                          type="text"
                          value={String(condition.value_field || '')}
                          placeholder={dragOverField === valueFieldDropKey ? 'Drop to insert path…' : 'e.g. expected_amount'}
                          onChange={(event) => updateCondition(idx, { value_field: event.target.value })}
                          onDragOver={(event) => handleDragOver(event, valueFieldDropKey)}
                          onDragLeave={(event) => handleDragLeave(event)}
                          onDrop={(event) => handleFilterConditionDrop(event, idx, 'value_field', 'value_field')}
                          className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === valueFieldDropKey
                            ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                            : 'border-slate-200 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                            }`}
                        />
                      </div>
                    ) : requiresCompareValue ? (
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Right Value
                        </label>
                        {dataType === 'boolean' ? (
                          <select
                            value={String(condition.value ?? 'true')}
                            onChange={(event) => updateCondition(idx, { value: event.target.value })}
                            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:focus:border-blue-400"
                          >
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        ) : (
                          <input
                            type={dataType === 'date' ? 'datetime-local' : (dataType === 'number' ? 'number' : 'text')}
                            value={String(condition.value ?? '')}
                            placeholder={dragOverField === valueDropKey
                              ? 'Drop to insert {{path}}…'
                              : dataType === 'number'
                                ? 'e.g. 500'
                                : dataType === 'date'
                                  ? 'e.g. 2026-05-07T13:45'
                                  : dataType === 'array'
                                    ? 'e.g. value or 2'
                                    : dataType === 'object'
                                      ? 'JSON object literal'
                                      : 'e.g. paid'}
                            onChange={(event) => updateCondition(idx, { value: event.target.value })}
                            onDragOver={(event) => handleDragOver(event, valueDropKey)}
                            onDragLeave={(event) => handleDragLeave(event)}
                            onDrop={(event) => handleFilterConditionDrop(event, idx, 'value', 'value')}
                            className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:placeholder:text-slate-700 ${dragOverField === valueDropKey
                              ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                              : 'border-slate-200 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-400'
                              }`}
                          />
                        )}
                      </div>
                    ) : null}

                    {usesStringComparison && (
                      <div className="space-y-1">
                        <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                          Case Sensitive
                        </label>
                        <select
                          value={String(caseSensitive)}
                          onChange={(event) => updateCondition(idx, { case_sensitive: event.target.value === 'true' })}
                          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:focus:border-blue-400"
                        >
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            <button
              type="button"
              onClick={addCondition}
              className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 py-2 text-xs font-bold text-slate-400 transition-all hover:border-blue-300 hover:text-blue-500 dark:border-slate-800 dark:text-slate-600 dark:hover:border-blue-900 dark:hover:text-blue-400"
            >
              <Plus size={12} strokeWidth={3} />
              Add Condition
            </button>
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
        const rawStringArrayValue = getModeAwareFieldValue(field, value);
        const stringArray = Array.isArray(rawStringArrayValue) ? rawStringArrayValue : [];
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
                    handleModeAwareFieldChange(field, next);
                  }}
                  onDragOver={(e) => handleDragOver(e, `${field.key}_${idx}`)}
                  onDragLeave={(e) => handleDragLeave(e)}
                  onDrop={(e) => handleArrayDrop(e, field.key, stringArray, idx)}
                  className={`w-full bg-slate-50 dark:bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none transition-all pr-8 ${dragOverField === `${field.key}_${idx}`
                    ? 'border-blue-400 ring-2 ring-blue-500/30 bg-blue-50/40 dark:bg-blue-900/10 dark:border-blue-500'
                    : 'border-slate-200 dark:border-slate-700 focus:border-blue-500 dark:focus:border-blue-400'
                    }`}
                />
                <button
                  onClick={() => {
                    const next = [...stringArray];
                    next.splice(idx, 1);
                    handleModeAwareFieldChange(field, next);
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                </button>
              </div>
            ))}
            <button
              onClick={() => handleModeAwareFieldChange(field, [...stringArray, ''])}
              className="w-full py-1.5 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-lg text-slate-400 dark:text-slate-600 text-[10px] font-bold hover:border-blue-300 dark:hover:border-blue-900 hover:text-blue-500 dark:hover:text-blue-400 transition-all flex items-center justify-center gap-2"
            >
              <Plus size={12} strokeWidth={3} />
              Add Parameter
            </button>
          </div>
        );

      case 'sheet_update_mappings': {
        const rawMappingsValue = getModeAwareFieldValue(field, value);
        const rawMappings = Array.isArray(rawMappingsValue) ? rawMappingsValue : [];
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
          handleModeAwareFieldChange(field, normalizedMappings);
        }

        const updateMapping = (index: number, patch: Record<string, any>) => {
          const next = [...normalizedMappings];
          next[index] = { ...next[index], ...patch };
          handleModeAwareFieldChange(field, next);
        };

        return (
          <div className="space-y-3">
            {normalizedMappings.map((mapping: any, idx: number) => (
              <div key={mapping.id || idx} className="p-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl space-y-2 relative group transition-colors">
                <button
                  onClick={() => {
                    const next = [...normalizedMappings];
                    next.splice(idx, 1);
                    handleModeAwareFieldChange(field, next);
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
              onClick={() => handleModeAwareFieldChange(field, [...normalizedMappings, { id: `mapping_${Date.now()}`, column: '', value: '' }])}
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
        const textareaDropPlaceholder = isPathPlaceholderForTextarea
          ? 'Drop to insert path…'
          : 'Drop to insert value…';
        const textareaValue = getModeAwareTextValue(field);
        return (
          <div className="relative">
            <textarea
              value={textareaValue}
              placeholder={dragOverField === field.key ? textareaDropPlaceholder : field.placeholder}
              onChange={(e) => handleModeAwareTextChange(field, e.target.value)}
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
        const textDropPlaceholder = isPathPlaceholderForText
          ? 'Drop to insert path…'
          : 'Drop to insert value…';
        const textValue = getModeAwareTextValue(field);
        return (
          <div className="relative">
            <input
              type="text"
              value={textValue}
              placeholder={dragOverField === field.key ? textDropPlaceholder : field.placeholder}
              onChange={(e) => handleModeAwareTextChange(field, e.target.value)}
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
    if (nodeType === 'merge') {
      const mode = String(config.mode || 'append').trim().toLowerCase();

      if (field.key === 'choose_branch') {
        return mode === 'choose_branch';
      }
      if (field.key === 'join_type') {
        return mode === 'combine_by_position' || mode === 'combine_by_fields';
      }
      if (field.key === 'input_1_field' || field.key === 'input_2_field') {
        return mode === 'combine_by_fields';
      }
      if (field.key === 'output_key') {
        return mode !== 'choose_branch' && mode !== 'combine';
      }
      return true;
    }

    if (nodeType === 'image_gen') {
      if (field.key === 'style') {
        return String(config.model || 'dall-e-3') === 'dall-e-3';
      }
      return true;
    }

    if (!['search_update_google_sheets', 'read_google_sheets'].includes(nodeType)) {
      return true;
    }

    const sourceType = String(config.spreadsheet_source_type || 'id').trim().toLowerCase();

    if (field.key === 'spreadsheet_id') return sourceType !== 'url';
    if (field.key === 'spreadsheet_url') return sourceType === 'url';
    if (nodeType === 'read_google_sheets') {
      return true;
    }

    const operation = normalizeSheetsOperation(config.operation, Boolean(config.upsert_if_not_found));

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
          <div key={field.key} className="group/field space-y-2">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-600">
              {field.label}
            </label>
            {renderField(field)}
            {field.helperText && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400">{field.helperText}</p>
            )}
            {field.imageTemplateHints && imageTemplateHints.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {imageTemplateHints.map((hint) => (
                  <button
                    key={hint}
                    type="button"
                    onClick={() => insertImageHint(field.key, hint)}
                    className="rounded-full border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 px-2.5 py-1 text-[10px] font-mono text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
                  >
                    {hint}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
};

export default ConfigForm;
