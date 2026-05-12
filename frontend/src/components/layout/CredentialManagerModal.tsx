import React, { useEffect, useMemo, useState } from 'react';
import { X, RefreshCw, Plus, KeyRound, Copy, Check, Trash2, Link as LinkIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { createPortal } from 'react-dom';
import { credentialService, CredentialItem } from '../../services/credentialService';
import { formatDateTimeInAppTimezone } from '../../utils/dateTime';

interface CredentialManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const APP_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'slack', label: 'Slack' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'gmail', label: 'Gmail' },
  { value: 'sheets', label: 'Google Sheets' },
  { value: 'docs', label: 'Google Docs' },
];

const APP_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  groq: 'Groq',
  telegram: 'Telegram',
  whatsapp: 'WhatsApp',
  slack: 'Slack',
  linkedin: 'LinkedIn',
  gmail: 'Gmail',
  sheets: 'Google Sheets',
  docs: 'Google Docs',
};

const APP_SECRET_FIELD: Record<string, { key: string; label: string; placeholder: string }> = {
  telegram: {
    key: 'api_key',
    label: 'Bot Token',
    placeholder: 'Telegram Bot Token (e.g. 123456789:AA...)',
  },
  slack: {
    key: 'webhook_url',
    label: 'Webhook URL',
    placeholder: 'https://hooks.slack.com/services/T000/B000/XXXXXXXX',
  },
  default: {
    key: 'api_key',
    label: 'API Key / Token',
    placeholder: 'Paste secret...',
  },
};

const CredentialManagerModal: React.FC<CredentialManagerModalProps> = ({ isOpen, onClose }) => {
  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isOAuthConnecting, setIsOAuthConnecting] = useState(false);
  const [appName, setAppName] = useState('openai');
  const [secret, setSecret] = useState('');
  const [description, setDescription] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [slackChannel, setSlackChannel] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const sortedCredentials = useMemo(
    () =>
      [...credentials].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [credentials],
  );
  const secretField = APP_SECRET_FIELD[appName] || APP_SECRET_FIELD.default;
  const isTelegram = appName === 'telegram';
  const isGmail = appName === 'gmail';
  const isSheets = appName === 'sheets';
  const isDocs = appName === 'docs';
  const isLinkedIn = appName === 'linkedin';
  const isOAuthConnectingApp = isGmail || isSheets || isDocs || isLinkedIn;

  const fetchCredentials = async () => {
    setIsLoading(true);
    try {
      const list = await credentialService.list();
      setCredentials(list);
    } catch (error) {
      console.error('Failed to load credentials:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    setSecret('');
    setDescription('');
    setTelegramChatId('');
    setSlackChannel('');
    setIsOAuthConnecting(false);
    void fetchCredentials();
  }, [isOpen]);

  useEffect(() => {
    if (!copiedId) return;
    const timer = window.setTimeout(() => setCopiedId(null), 1400);
    return () => window.clearTimeout(timer);
  }, [copiedId]);

  useEffect(() => {
    if (appName !== 'telegram') {
      setTelegramChatId('');
    }
    if (appName !== 'slack') {
      setSlackChannel('');
    }
    setSecret('');
    setDescription('');
  }, [appName]);

  const handleCreate = async () => {
    if (isOAuthConnectingApp) {
      toast.error('OAuth credentials are connected through the button above.');
      return;
    }
    const trimmed = secret.trim();
    const trimmedDescription = description.trim();
    if (!trimmed) {
      toast.error('Please enter API key / token');
      return;
    }
    const trimmedChatId = telegramChatId.trim();
    if (isTelegram && !trimmedChatId) {
      toast.error('Please enter Telegram Chat ID');
      return;
    }
    if (appName === 'slack' && !slackChannel.trim()) {
      toast.error('Please enter Slack channel');
      return;
    }
    setIsSaving(true);
    try {
      await credentialService.create({
        app_name: appName,
        description: trimmedDescription || undefined,
        token_data: {
          [secretField.key]: trimmed,
          ...(isTelegram ? { chat_id: trimmedChatId } : {}),
          ...(appName === 'slack' ? { channel: slackChannel.trim() } : {}),
        },
      });
      setSecret('');
      setDescription('');
      setTelegramChatId('');
      await fetchCredentials();
      toast.success('Credential saved');
    } catch (error) {
      console.error('Failed to create credential:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleOAuthConnect = async () => {
    if (!isOAuthConnectingApp) return;
    setIsOAuthConnecting(true);
    try {
      const redirectUri = isLinkedIn
        ? `${window.location.origin}/app/oauth/linkedin/callback`
        : `${window.location.origin}/app/oauth/google/callback`;
      const result = isLinkedIn
        ? await credentialService.startLinkedInOAuth(redirectUri)
        : await credentialService.startGoogleOAuth(
            isGmail ? 'gmail' : (isSheets ? 'sheets' : 'docs'),
            redirectUri,
          );
      window.location.href = result.auth_url;
    } catch (error) {
      console.error('Failed to start OAuth:', error);
      toast.error(`Could not start ${isLinkedIn ? 'LinkedIn' : 'Google'} OAuth flow.`);
      setIsOAuthConnecting(false);
    }
  };

  const copyCredentialId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedId(id);
      toast.success('Credential ID copied');
    } catch (error) {
      toast.error('Could not copy credential ID');
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this credential?')) return;
    try {
      await credentialService.remove(id);
      await fetchCredentials();
      toast.success('Credential deleted');
    } catch (error) {
      console.error('Failed to delete credential:', error);
    }
  };

  if (!isOpen) return null;
  if (typeof document === 'undefined') return null;

  const modalContent = (
    <div
      className="fixed inset-0 z-[100001] bg-slate-900/45 backdrop-blur-[2px] flex items-center justify-center p-3 md:p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[1500px] h-[94vh] md:h-[92vh] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.24)] overflow-hidden flex flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Account
            </p>
            <h3 className="text-lg font-black text-slate-900 dark:text-slate-100 mt-0.5">
              Credential Manager
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid flex-1 min-h-0 grid-cols-1 md:grid-cols-[380px_1fr]">
          <div className="p-5 border-r border-slate-200 dark:border-slate-800 overflow-y-auto">
            <div className="flex items-center gap-2 mb-4">
              <KeyRound size={15} className="text-blue-600 dark:text-blue-400" />
              <p className="text-xs font-black uppercase tracking-[0.1em] text-slate-600 dark:text-slate-300">
                Add Credential
              </p>
            </div>

            <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">
              App
            </label>
            <select
              value={appName}
              onChange={(event) => setAppName(event.target.value)}
              className="w-full mb-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/40"
            >
              {APP_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {isOAuthConnectingApp && (
              <button
                type="button"
                onClick={() => void handleOAuthConnect()}
                disabled={isOAuthConnecting}
                className="w-full mb-4 flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500 text-white px-4 py-2 text-sm font-black uppercase tracking-[0.08em] transition-colors"
              >
                <LinkIcon size={14} />
                {isOAuthConnecting ? 'Connecting...' : isLinkedIn ? 'Connect With LinkedIn OAuth' : 'Connect With Google OAuth'}
              </button>
            )}
            {isOAuthConnectingApp && (
              <p className="mb-3 text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {isLinkedIn
                  ? 'LinkedIn credentials are OAuth-only. Click the button above to connect your LinkedIn account.'
                  : 'Google credentials are OAuth-only. Click the button above to connect your Google account.'}
              </p>
            )}
            {!isOAuthConnectingApp && (
              <>
                <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">
                  {secretField.label}
                </label>
                <input
                  type="password"
                  name="credential-manager-secret"
                  autoComplete="new-password"
                  spellCheck={false}
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  placeholder={secretField.placeholder}
                  className="w-full mb-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </>
            )}
            {isTelegram && (
              <>
                <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">
                  Chat ID
                </label>
                <input
                  type="text"
                  name="credential-manager-telegram-chat-id"
                  autoComplete="off"
                  spellCheck={false}
                  value={telegramChatId}
                  onChange={(event) => setTelegramChatId(event.target.value)}
                  placeholder="e.g. 123456789 or -1001234567890"
                  className="w-full mb-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </>
            )}
            {appName === 'slack' && (
              <>
                <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">
                  Slack Channel
                </label>
                <input
                  type="text"
                  name="credential-manager-slack-channel"
                  autoComplete="off"
                  spellCheck={false}
                  value={slackChannel}
                  onChange={(event) => setSlackChannel(event.target.value)}
                  placeholder="e.g. #general or @someone"
                  className="w-full mb-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </>
            )}
            {!isOAuthConnectingApp && (
              <>
                <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">
                  Description (Optional)
                </label>
                <textarea
                  name="credential-manager-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Why this credential exists, where it is used, who owns it..."
                  rows={3}
                  maxLength={300}
                  className="w-full mb-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/40 resize-y"
                />
                <p className="mb-4 text-[10px] text-slate-500 dark:text-slate-400 text-right">
                  {description.trim().length}/300
                </p>
              </>
            )}

            {!isOAuthConnectingApp && (
              <button
                type="button"
                onClick={handleCreate}
                disabled={isSaving}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:text-slate-500 text-white px-4 py-2 text-sm font-black uppercase tracking-[0.08em] transition-colors"
              >
                <Plus size={14} />
                {isSaving ? 'Saving...' : 'Save Credential'}
              </button>
            )}

            <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
              Use saved credential IDs in node config where `credential_id` is required.
            </p>
          </div>

          <div className="p-5 min-h-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-black uppercase tracking-[0.1em] text-slate-600 dark:text-slate-300">
                Saved Credentials
              </p>
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                  {sortedCredentials.length} total
                </span>
                <button
                  type="button"
                  onClick={() => void fetchCredentials()}
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400"
                >
                  <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
                  Refresh
                </button>
              </div>
            </div>

            {isLoading ? (
              <div className="h-40 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                Loading credentials...
              </div>
            ) : sortedCredentials.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl">
                No credentials yet.
              </div>
            ) : (
              <div className="space-y-3 pr-1">
                {sortedCredentials.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/60 shadow-sm p-3.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <span className="inline-flex items-center rounded-full bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.08em]">
                          {APP_LABELS[item.app_name] || item.app_name}
                        </span>
                        <p className="mt-1 text-[12px] font-semibold text-slate-800 dark:text-slate-100 break-words">
                          {item.display_name || 'Credential'}
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-slate-500 dark:text-slate-400">
                        {formatDateTimeInAppTimezone(item.created_at)}
                      </span>
                    </div>

                    {item.description && (
                      <p className="mt-1.5 text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed break-words">
                        {item.description}
                      </p>
                    )}

                    <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-900/40 px-2.5 py-2">
                      <p className="text-[10px] uppercase tracking-[0.08em] font-bold text-slate-500 dark:text-slate-400 mb-1">
                        Credential ID
                      </p>
                      <code className="block text-[11px] text-slate-700 dark:text-slate-200 break-all leading-relaxed">
                        {item.id}
                      </code>
                    </div>

                    <div className="mt-3">
                      <p className="text-[10px] uppercase tracking-[0.08em] font-bold text-slate-500 dark:text-slate-400 mb-1.5">
                        Actions
                      </p>
                      <div className="flex flex-col sm:flex-row gap-2">
                        <button
                          type="button"
                          onClick={() => void copyCredentialId(item.id)}
                          className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-[10px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200 border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        >
                          {copiedId === item.id ? <Check size={12} /> : <Copy size={12} />}
                          {copiedId === item.id ? 'Copied ID' : 'Copy ID'}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(item.id)}
                          className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-[10px] font-bold uppercase tracking-wider text-rose-700 border border-rose-300 hover:bg-rose-50 dark:border-rose-900/40 dark:text-rose-300 dark:hover:bg-rose-900/20 transition-colors"
                        >
                          <Trash2 size={12} />
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

export default CredentialManagerModal;
