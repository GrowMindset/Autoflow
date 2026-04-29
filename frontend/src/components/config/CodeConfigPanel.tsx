import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import api from '../../services/api';
import { CredentialItem, credentialService } from '../../services/credentialService';

declare global {
  interface Window {
    monaco?: any;
    require?: any;
  }
}

const MONACO_LOADER_URL = 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js';
const MONACO_VS_PATH = 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs';

const DEFAULT_CODE: Record<string, string> = {
  python: '# input_data is available as a dict\n# assign your result to: output\noutput = input_data',
  javascript: '// input_data is available as an object\n// assign your result to: output\nconst output = { ...input_data };',
};

let monacoLoadPromise: Promise<any> | null = null;

const loadMonaco = () => {
  if (window.monaco) return Promise.resolve(window.monaco);
  if (monacoLoadPromise) return monacoLoadPromise;

  monacoLoadPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>(
      `script[src="${MONACO_LOADER_URL}"]`,
    );

    const configureAndLoad = () => {
      if (!window.require) {
        reject(new Error('Monaco loader did not initialize.'));
        return;
      }

      window.require.config({ paths: { vs: MONACO_VS_PATH } });
      window.require(['vs/editor/editor.main'], () => {
        if (window.monaco) {
          resolve(window.monaco);
        } else {
          reject(new Error('Monaco editor failed to load.'));
        }
      });
    };

    if (existingScript) {
      existingScript.addEventListener('load', configureAndLoad, { once: true });
      existingScript.addEventListener('error', reject, { once: true });
      if (window.require) configureAndLoad();
      return;
    }

    const script = document.createElement('script');
    script.src = MONACO_LOADER_URL;
    script.async = true;
    script.onload = configureAndLoad;
    script.onerror = () => reject(new Error('Failed to load Monaco editor.'));
    document.head.appendChild(script);
  });

  return monacoLoadPromise;
};

interface CodeConfigPanelProps {
  config: Record<string, any>;
  onChange: (patch: Record<string, any>) => void;
}

const normalizeLanguage = (language: any): 'python' | 'javascript' =>
  language === 'javascript' ? 'javascript' : 'python';

const CodeConfigPanel: React.FC<CodeConfigPanelProps> = ({ config, onChange }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const [loadError, setLoadError] = useState('');
  const [showPrompt, setShowPrompt] = useState(false);
  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [isLoadingCredentials, setIsLoadingCredentials] = useState(false);
  const [selectedCredentialId, setSelectedCredentialId] = useState('');
  const [showCredentialForm, setShowCredentialForm] = useState(false);
  const [newCredentialKey, setNewCredentialKey] = useState('');
  const [isSavingCredential, setIsSavingCredential] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const language = normalizeLanguage(config.language);
  const code = typeof config.code === 'string' && config.code.length > 0
    ? config.code
    : DEFAULT_CODE[language];
  const editorLanguage = language === 'python' ? 'python' : 'javascript';

  const options = useMemo(
    () => ({
      minimap: { enabled: false },
      fontSize: 13,
      lineNumbers: 'on',
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      automaticLayout: true,
      tabSize: 2,
      roundedSelection: false,
      padding: { top: 12, bottom: 12 },
    }),
    [],
  );

  useEffect(() => {
    let cancelled = false;

    loadMonaco()
      .then((monaco) => {
        if (cancelled || !containerRef.current) return;
        monacoRef.current = monaco;
        if (editorRef.current) return;

        editorRef.current = monaco.editor.create(containerRef.current, {
          value: code,
          language: editorLanguage,
          theme: document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs',
          ...options,
        });

        editorRef.current.onDidChangeModelContent(() => {
          onChange({ code: editorRef.current.getValue() });
        });
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      });

    return () => {
      cancelled = true;
      editorRef.current?.dispose();
      editorRef.current = null;
    };
  }, []);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const currentValue = editor.getValue();
    if (currentValue !== code) {
      editor.setValue(code);
    }
  }, [code]);

  useEffect(() => {
    const monaco = monacoRef.current;
    const editor = editorRef.current;
    if (!monaco || !editor) return;
    const model = editor.getModel();
    if (model) {
      monaco.editor.setModelLanguage(model, editorLanguage);
    }
  }, [editorLanguage]);

  const fetchCredentials = async () => {
    setIsLoadingCredentials(true);
    try {
      const list = await credentialService.list('openai');
      setCredentials(list);
      if (!selectedCredentialId && list.length === 1) {
        setSelectedCredentialId(list[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch OpenAI credentials', error);
      setAiError('Could not load saved OpenAI credentials.');
    } finally {
      setIsLoadingCredentials(false);
    }
  };

  useEffect(() => {
    void fetchCredentials();
  }, []);

  const handleLanguageChange = (nextLanguage: 'python' | 'javascript') => {
    if (nextLanguage === language) return;
    const currentCode = typeof config.code === 'string' ? config.code : '';
    const shouldSwapDefault =
      !currentCode.trim() ||
      currentCode === DEFAULT_CODE.python ||
      currentCode === DEFAULT_CODE.javascript;

    onChange({
      language: nextLanguage,
      code: shouldSwapDefault ? DEFAULT_CODE[nextLanguage] : currentCode,
    });
  };

  const handleGenerateToggle = () => {
    setAiError(null);
    setShowPrompt(true);
    void fetchCredentials();
  };

  const handleSaveCredential = async () => {
    const trimmedKey = newCredentialKey.trim();
    if (!trimmedKey) return;

    setIsSavingCredential(true);
    setAiError(null);
    try {
      const credential = await credentialService.create({
        app_name: 'openai',
        token_data: {
          api_key: trimmedKey,
          provider: 'api_key',
        },
      });
      setCredentials((current) => [credential, ...current.filter((item) => item.id !== credential.id)]);
      setSelectedCredentialId(credential.id);
      setApiKey('');
      setNewCredentialKey('');
      setShowCredentialForm(false);
    } catch (error) {
      console.error('Failed to save OpenAI credential', error);
      setAiError('Could not save OpenAI credential.');
    } finally {
      setIsSavingCredential(false);
    }
  };

  const handleGenerate = async () => {
    const trimmedApiKey = apiKey.trim();
    const credentialId = selectedCredentialId.trim();
    if ((!credentialId && !trimmedApiKey) || !aiPrompt.trim()) return;
    setIsGenerating(true);
    setAiError(null);

    try {
      const response = await api.post('/ai/generate-code', {
        prompt: aiPrompt.trim(),
        language,
        ...(credentialId ? { credential_id: credentialId } : { api_key: trimmedApiKey }),
      });
      const generatedCode = String(response.data?.code || '');
      if (editorRef.current) {
        editorRef.current.setValue(generatedCode);
      }
      onChange({ code: generatedCode });
      setShowPrompt(false);
      setAiPrompt('');
    } catch (error) {
      console.error('Code generation failed:', error);
      setAiError('Generation failed. Check your API key or try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
          Language
        </label>
        <div className="grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-1">
          {(['python', 'javascript'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => handleLanguageChange(option)}
              className={`rounded-xl px-4 py-2 text-xs font-black uppercase tracking-widest transition-all ${
                language === option
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-800'
              }`}
            >
              {option === 'python' ? 'Python' : 'JavaScript'}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <button
          type="button"
          onClick={handleGenerateToggle}
          className="group flex w-full items-center justify-between gap-4 rounded-2xl border border-purple-200 dark:border-purple-800/60 bg-gradient-to-r from-purple-600 via-fuchsia-600 to-indigo-600 px-4 py-3 text-left shadow-[0_14px_30px_rgba(147,51,234,0.24)] transition-all hover:-translate-y-0.5 hover:shadow-[0_18px_38px_rgba(147,51,234,0.32)] active:translate-y-0 disabled:opacity-60"
          disabled={isGenerating}
        >
          <span className="flex min-w-0 flex-col">
            <span className="text-xs font-black uppercase tracking-widest text-white">
              Generate with AI
            </span>
            <span className="mt-0.5 text-[11px] font-semibold normal-case tracking-normal text-purple-100">
              Describe the logic and insert ready-to-edit code into the editor.
            </span>
          </span>
          <span className="shrink-0 rounded-full border border-white/30 bg-white/15 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-white transition-colors group-hover:bg-white/25">
            Try it
          </span>
        </button>

        {showPrompt && (
          <div className="flex flex-col gap-3 rounded-2xl border border-purple-100 dark:border-purple-900/40 bg-purple-50/60 dark:bg-purple-900/10 p-3">
            <div className="space-y-2">
              <label className="text-[9px] font-black uppercase tracking-widest text-purple-700 dark:text-purple-300">
                OpenAI credential
              </label>
              <div className="flex gap-2">
                <select
                  value={selectedCredentialId}
                  onChange={(event) => {
                    setSelectedCredentialId(event.target.value);
                    if (event.target.value) setApiKey('');
                  }}
                  disabled={isGenerating || isLoadingCredentials}
                  className="min-w-0 flex-1 rounded-xl border border-purple-100 dark:border-purple-900/40 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 outline-none transition-all focus:border-purple-400 focus:ring-2 focus:ring-purple-500/20 disabled:opacity-60"
                >
                  <option value="">
                    {isLoadingCredentials ? 'Loading credentials...' : 'Use one-time API key...'}
                  </option>
                  {credentials.map((credential) => (
                    <option key={credential.id} value={credential.id}>
                      {(credential.display_name || credential.app_name)} - {credential.id.slice(0, 8)}...
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    setShowCredentialForm((current) => !current);
                    setAiError(null);
                  }}
                  disabled={isGenerating}
                  className="inline-flex h-10 items-center rounded-xl bg-purple-600 px-3 text-xs font-black uppercase tracking-widest text-white transition-colors hover:bg-purple-700 disabled:opacity-50"
                >
                  Add
                </button>
              </div>
              {credentials.length > 0 && (
                <p className="text-[11px] text-purple-700/80 dark:text-purple-300/80">
                  Saved OpenAI credentials are loaded from your credential store.
                </p>
              )}
            </div>

            {showCredentialForm && (
              <div className="flex gap-2 rounded-xl border border-purple-100 dark:border-purple-900/40 bg-white/70 dark:bg-slate-950/70 p-2">
                <input
                  type="password"
                  value={newCredentialKey}
                  onChange={(event) => setNewCredentialKey(event.target.value)}
                  disabled={isSavingCredential || isGenerating}
                  placeholder="New OpenAI API key"
                  className="min-w-0 flex-1 rounded-lg border border-purple-100 dark:border-purple-900/40 bg-white dark:bg-slate-950 px-3 py-2 text-xs text-slate-700 dark:text-slate-200 outline-none transition-all focus:border-purple-400 disabled:opacity-60"
                />
                <button
                  type="button"
                  onClick={handleSaveCredential}
                  disabled={!newCredentialKey.trim() || isSavingCredential || isGenerating}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 dark:bg-slate-100 px-3 text-xs font-bold text-white dark:text-slate-900 transition-colors disabled:opacity-50"
                >
                  {isSavingCredential && <Loader2 size={13} className="animate-spin" />}
                  Save
                </button>
              </div>
            )}

            {!selectedCredentialId && (
              <input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                disabled={isGenerating}
                placeholder="One-time OpenAI API key"
                className="w-full rounded-xl border border-purple-100 dark:border-purple-900/40 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 outline-none transition-all focus:border-purple-400 focus:ring-2 focus:ring-purple-500/20 disabled:opacity-60"
              />
            )}

            <div className="flex items-center gap-2">
              <input
                type="text"
                value={aiPrompt}
                onChange={(event) => setAiPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && aiPrompt.trim() && !isGenerating) {
                    event.preventDefault();
                    void handleGenerate();
                  }
                }}
                disabled={isGenerating}
                placeholder="e.g. find factorial of a number"
                className="min-w-0 flex-1 rounded-xl border border-purple-100 dark:border-purple-900/40 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-700 dark:text-slate-200 outline-none transition-all focus:border-purple-400 focus:ring-2 focus:ring-purple-500/20 disabled:opacity-60"
              />
              <button
                type="button"
                onClick={handleGenerate}
                disabled={(!selectedCredentialId.trim() && !apiKey.trim()) || !aiPrompt.trim() || isGenerating}
                className="inline-flex h-9 items-center gap-2 rounded-xl bg-slate-900 dark:bg-slate-100 px-3 text-xs font-bold text-white dark:text-slate-900 transition-colors hover:bg-slate-800 dark:hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isGenerating && <Loader2 size={14} className="animate-spin" />}
                Generate
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowPrompt(false);
                  setAiPrompt('');
                  setAiError(null);
                }}
                disabled={isGenerating}
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-purple-100 dark:border-purple-900/40 bg-white dark:bg-slate-950 text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-100 disabled:opacity-50"
                title="Close"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}

        {aiError && (
          <p className="text-[11px] font-semibold text-rose-600 dark:text-rose-400">
            {aiError}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
          Code
        </label>
        <div className="min-h-[300px] overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950">
          {loadError ? (
            <textarea
              value={code}
              onChange={(event) => onChange({ code: event.target.value })}
              className="min-h-[300px] w-full resize-y bg-white dark:bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-700 dark:text-slate-200 outline-none"
              spellCheck={false}
            />
          ) : (
            <div ref={containerRef} className="min-h-[300px] h-[300px]" />
          )}
        </div>
        {loadError && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400">
            Monaco could not load, so a plain editor is shown.
          </p>
        )}
      </div>
    </div>
  );
};

export default CodeConfigPanel;
