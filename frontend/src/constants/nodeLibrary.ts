export interface NodeDefinition {
  type: string;
  label: string;
  category: 'trigger' | 'action' | 'transform' | 'ai';
  description: string;
  default_config: Record<string, any>;
  is_dummy: boolean;
  icon?: string;
  phase?: number;
}

export const NODE_LIBRARY: Record<string, NodeDefinition[]> = {
  trigger: [
    {
      type: 'manual_trigger',
      label: 'Manual Trigger',
      category: 'trigger',
      description: 'Start the workflow manually with one click.',
      default_config: {},
      is_dummy: false,
    },
    {
      type: 'form_trigger',
      label: 'Form Trigger',
      category: 'trigger',
      description: 'Trigger the workflow when a form is submitted.',
      default_config: {
        form_title: 'Form Submission',
        form_description: '',
        fields: [
          {
            name: 'email',
            label: 'Email',
            type: 'email',
            required: true,
          },
        ],
      },
      is_dummy: false,
    },
    {
      type: 'webhook_trigger',
      label: 'Webhook Trigger',
      category: 'trigger',
      description: 'Trigger the workflow via an HTTP request.',
      default_config: {
        path: '',
        method: 'POST',
      },
      is_dummy: false,
    },
    {
      type: 'workflow_trigger',
      label: 'Workflow Trigger',
      category: 'trigger',
      description: 'Trigger this workflow from another workflow.',
      default_config: {},
      is_dummy: false,
    },
  ],
  action: [
    {
      type: 'get_gmail_message',
      label: 'Get Gmail Message',
      category: 'action',
      description: 'Retrieve messages from a Gmail account.',
      default_config: {
        credential_id: '',
        folder: 'INBOX',
        query: '',
        limit: '10',
        unread_only: false,
        include_body: false,
        mark_as_read: false,
      },
      is_dummy: false,
      icon: 'gmail',
    },
    {
      type: 'send_gmail_message',
      label: 'Send Gmail Message',
      category: 'action',
      description: 'Send an email through a Gmail account.',
      default_config: {
        credential_id: '',
        to: '',
        cc: '',
        bcc: '',
        reply_to: '',
        subject: '',
        body: '',
        is_html: false,
      },
      is_dummy: false,
      icon: 'gmail',
    },
    {
      type: 'create_google_sheets',
      label: 'Create Google Sheets',
      category: 'action',
      description: 'Create a new Google Spreadsheet.',
      default_config: {
        credential_id: '',
        title: '',
        sheet_name: '',
      },
      is_dummy: false,
      icon: 'sheets',
    },
    {
      type: 'search_update_google_sheets',
      label: 'Search & Update Google Sheets',
      category: 'action',
      description: 'Search and update rows in a Google Spreadsheet.',
      default_config: {
        credential_id: '',
        spreadsheet_id: '',
        sheet_name: 'Sheet1',
        search_column: '',
        search_value: '',
        update_column: '',
        update_value: '',
      },
      is_dummy: false,
      icon: 'sheets',
    },
    {
      type: 'create_google_docs',
      label: 'Create Google Docs',
      category: 'action',
      description: 'Create a new Google Doc.',
      default_config: {
        credential_id: '',
        title: '',
        initial_content: '',
      },
      is_dummy: false,
      icon: 'docs',
    },
    {
      type: 'update_google_docs',
      label: 'Update Google Docs',
      category: 'action',
      description: 'Append or replace content in a Google Doc.',
      default_config: {
        credential_id: '',
        document_id: '',
        operation: 'append_text',
        text: '',
        match_text: '',
        match_case: false,
      },
      is_dummy: false,
      icon: 'docs',
    },
    {
      type: 'telegram',
      label: 'Telegram Message',
      category: 'action',
      description: 'Send a message via Telegram.',
      default_config: {
        credential_id: '',
        message: '',
        parse_mode: '',
      },
      is_dummy: false,
      icon: 'telegram',
    },
    {
      type: 'whatsapp',
      label: 'WhatsApp Message',
      category: 'action',
      description: 'Send a message via WhatsApp Cloud API.',
      default_config: {
        credential_id: '',
        to_number: '',
        template_name: '',
        template_params: [],
        language_code: 'en_US',
      },
      is_dummy: false,
      icon: 'whatsapp',
    },
    {
      type: 'linkedin',
      label: 'LinkedIn Post',
      category: 'action',
      description: 'Create a post on LinkedIn.',
      default_config: {},
      is_dummy: true,
      icon: 'linkedin',
      phase: 3,
    },
  ],
  transform: [
    {
      type: 'if_else',
      label: 'If Else',
      category: 'transform',
      description: 'Split the workflow based on conditions.',
      default_config: {
        field: '',
        operator: 'equals',
        value: '',
      },
      is_dummy: false,
    },
    {
      type: 'switch',
      label: 'Switch',
      category: 'transform',
      description: 'Route the workflow to multiple paths.',
      default_config: {
        field: '',
        cases: [
          {
            label: '',
            operator: 'equals',
            value: '',
          },
        ],
        default_case: 'default',
      },
      is_dummy: false,
    },
    {
      type: 'merge',
      label: 'Merge',
      category: 'transform',
      description: 'Combine data from multiple branches.',
      default_config: {},
      is_dummy: false,
    },
    {
      type: 'filter',
      label: 'Filter',
      category: 'transform',
      description: 'Remove items from the data stream.',
      default_config: {
        input_key: '',
        field: '',
        operator: 'equals',
        value: '',
      },
      is_dummy: false,
    },
    {
      type: 'datetime_format',
      label: 'Date Time Format',
      category: 'transform',
      description: 'Standardize date and time formats.',
      default_config: {
        field: '',
        output_format: '%Y-%m-%d',
      },
      is_dummy: false,
    },
    {
      type: 'split_in',
      label: 'Split In',
      category: 'transform',
      description: 'Iterate through a collection of items.',
      default_config: {
        input_key: '',
      },
      is_dummy: false,
    },
    {
      type: 'split_out',
      label: 'Split Out',
      category: 'transform',
      description: 'Collect iterated items.',
      default_config: {
        output_key: 'results',
      },
      is_dummy: false,
    },
    {
      type: 'aggregate',
      label: 'Aggregate',
      category: 'transform',
      description: 'Combine multiple items into one array.',
      default_config: {
        input_key: '',
        field: '',
        operation: 'sum',
        output_key: '',
      },
      is_dummy: false,
    },
  ],
  ai: [
    {
      type: 'ai_agent',
      label: 'AI Agent',
      category: 'ai',
      description: 'Advanced AI processing and analysis.',
      default_config: {
        system_prompt: '',
        command: '',
        response_enhancement: 'auto',
      },
      is_dummy: false,
    },
    {
      type: 'chat_model_openai',
      label: 'Chat Model (OpenAI)',
      category: 'ai',
      description: 'Configure an OpenAI chat model.',
      default_config: {
        credential_id: '',
        model: 'gpt-4o',
        temperature: 0.7,
      },
      is_dummy: false,
    },
    {
      type: 'chat_model_groq',
      label: 'Chat Model (Groq)',
      category: 'ai',
      description: 'Configure a Groq chat model.',
      default_config: {
        credential_id: '',
        model: 'llama-3.3-70b-versatile',
        temperature: 0.7,
      },
      is_dummy: false,
    },
  ],
};

export const CATEGORY_STYLES = {
  trigger: 'border-l-4 border-emerald-500 bg-white text-slate-700 hover:bg-slate-50',
  action: 'border-l-4 border-blue-500 bg-white text-slate-700 hover:bg-slate-50',
  transform: 'border-l-4 border-amber-500 bg-white text-slate-700 hover:bg-slate-50',
  ai: 'border-l-4 border-purple-500 bg-white text-slate-700 hover:bg-slate-50',
};

export const CATEGORY_ACCENTS = {
  trigger: '#10b981', // emerald-500
  action: '#3b82f6', // blue-500
  transform: '#f59e0b', // amber-500
  ai: '#a855f7', // purple-500
};
