export type NodeSettingsVisibility = {
  onError: boolean;
  retryOnFail: boolean;
  notes: boolean;
};

export const DEFAULT_NODE_SETTINGS = {
  on_error: 'stop',
  retry_on_fail: false,
  retry_count: 3,
  notes: '',
  display_note: false,
};

export const NODE_SETTINGS_CONFIG: Record<string, NodeSettingsVisibility> = {
  manual_trigger: { onError: false, retryOnFail: false, notes: true },
  form_trigger: { onError: false, retryOnFail: false, notes: true },
  webhook_trigger: { onError: false, retryOnFail: false, notes: true },
  schedule_trigger: { onError: false, retryOnFail: false, notes: true },
  workflow_trigger: { onError: false, retryOnFail: false, notes: true },
  execute_workflow: { onError: true, retryOnFail: true, notes: true },
  code: { onError: true, retryOnFail: false, notes: true },
  if_else: { onError: true, retryOnFail: true, notes: true },
  switch: { onError: true, retryOnFail: true, notes: true },
  filter: { onError: true, retryOnFail: true, notes: true },
  limit: { onError: true, retryOnFail: true, notes: true },
  sort: { onError: true, retryOnFail: true, notes: true },
  merge: { onError: true, retryOnFail: true, notes: true },
  aggregate: { onError: true, retryOnFail: true, notes: true },
  split_in: { onError: true, retryOnFail: true, notes: true },
  split_out: { onError: true, retryOnFail: true, notes: true },
  datetime_format: { onError: true, retryOnFail: true, notes: true },
  delay: { onError: true, retryOnFail: true, notes: true },
  ai_agent: { onError: true, retryOnFail: true, notes: true },
  image_gen: { onError: true, retryOnFail: true, notes: true },
  chat_model_openai: { onError: true, retryOnFail: false, notes: true },
  chat_model_groq: { onError: true, retryOnFail: false, notes: true },
  gmail_get: { onError: true, retryOnFail: true, notes: true },
  gmail_send: { onError: true, retryOnFail: true, notes: true },
  get_gmail_message: { onError: true, retryOnFail: true, notes: true },
  send_gmail_message: { onError: true, retryOnFail: true, notes: true },
  create_gmail_draft: { onError: true, retryOnFail: true, notes: true },
  add_gmail_label: { onError: true, retryOnFail: true, notes: true },
  google_sheets_create: { onError: true, retryOnFail: true, notes: true },
  read_google_sheets: { onError: true, retryOnFail: true, notes: true },
  google_sheets_search_update: { onError: true, retryOnFail: true, notes: true },
  create_google_sheets: { onError: true, retryOnFail: true, notes: true },
  search_update_google_sheets: { onError: true, retryOnFail: true, notes: true },
  create_google_docs: { onError: true, retryOnFail: true, notes: true },
  read_google_docs: { onError: true, retryOnFail: true, notes: true },
  update_google_docs: { onError: true, retryOnFail: true, notes: true },
  telegram: { onError: true, retryOnFail: true, notes: true },
  whatsapp: { onError: true, retryOnFail: true, notes: true },
  linkedin: { onError: true, retryOnFail: true, notes: true },
  slack_send_message: { onError: true, retryOnFail: true, notes: true },
  http_request: { onError: true, retryOnFail: true, notes: true },
  file_read: { onError: true, retryOnFail: true, notes: true },
  file_write: { onError: true, retryOnFail: true, notes: true },
};

export const getNodeSettingsVisibility = (
  nodeType: string,
  category?: string,
): NodeSettingsVisibility => {
  const configured = NODE_SETTINGS_CONFIG[nodeType];
  if (configured) return configured;

  if (category === 'trigger') {
    return { onError: false, retryOnFail: false, notes: true };
  }

  return { onError: true, retryOnFail: category !== 'utility', notes: true };
};
