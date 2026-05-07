import React, { useState, useRef, useEffect } from 'react';
import { X, Send, Square, Sparkles, User, Bot, Loader2, Check, Eye, CheckCircle2, XCircle, Trash2, Copy, ClipboardCheck, ChevronDown } from 'lucide-react';
import toast from 'react-hot-toast';
import { AssistantInteractionMode, Message } from '../../services/aiService';

interface AIWorkflowChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  messages: Message[];
  onSendMessage: (content: string) => void;
  onStopGeneration: () => void;
  interactionMode: AssistantInteractionMode;
  onInteractionModeChange: (mode: AssistantInteractionMode) => void;
  onClearHistory: () => void;
  onReviewWorkflow: (workflow: any) => void;
  onAcceptReviewedWorkflow: (workflow: any) => void;
  onDiscardReviewedWorkflow: (workflow: any) => void;
  reviewedWorkflowSignature: string | null;
  isLoading: boolean;
  width: number;
  onResizeStart: (e: React.MouseEvent<HTMLDivElement>) => void;
  style?: React.CSSProperties;
}

const BUILD_EXAMPLE_PROMPTS = [
  'Create a workflow that classifies support ticket sentiment and routes negative ones to Telegram.',
  'Generate a form trigger flow that summarizes feedback with AI and logs the result.',
  'Create a workflow that generates the linkedIn post that takes form trigger and takes values post title, tone, type of post and generates post and sent it to linkedIn post',
];

const ASK_EXAMPLE_PROMPTS = [
  'I want to create customer support automation. Which trigger should I choose and why?',
  'In ai_agent node, what is the difference between system_prompt and command?',
  'How should I map Telegram message parameters using {{output.summary}} and other fields?',
];

const AIWorkflowChatPanel: React.FC<AIWorkflowChatPanelProps> = ({
  isOpen,
  onClose,
  messages,
  onSendMessage,
  onStopGeneration,
  interactionMode,
  onInteractionModeChange,
  onClearHistory,
  onReviewWorkflow,
  onAcceptReviewedWorkflow,
  onDiscardReviewedWorkflow,
  reviewedWorkflowSignature,
  isLoading,
  width,
  onResizeStart,
  style,
}) => {
  const [input, setInput] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const copyResetTimerRef = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const examplePrompts = interactionMode === 'ask' ? ASK_EXAMPLE_PROMPTS : BUILD_EXAMPLE_PROMPTS;
  const inputPlaceholder = interactionMode === 'ask'
    ? 'Ask anything about Autoflow nodes, triggers, and parameters...'
    : 'Describe the workflow you want to build...';

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const updateScrollState = () => {
    const container = scrollRef.current;
    if (!container) return;
    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    setShowScrollToBottom(distanceToBottom > 64);
  };

  useEffect(() => {
    updateScrollState();
  }, [messages, isLoading]);

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
    };
  }, []);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  const handleExamplePromptClick = (prompt: string) => {
    if (isLoading) return;
    setInput(prompt);
    inputRef.current?.focus();
  };

  const getMessageTimeLabel = (timestamp: string) => {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const handleCopyMessage = async (messageId: string, content: string) => {
    const normalized = String(content || '').trim();
    if (!normalized) return;
    try {
      await navigator.clipboard.writeText(normalized);
      setCopiedMessageId(messageId);
      toast.success('Message copied');
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedMessageId((current) => (current === messageId ? null : current));
      }, 1800);
    } catch (error) {
      toast.error('Could not copy message');
    }
  };

  const handleScrollToBottom = () => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  };

  if (!isOpen) return null;

  return (
    <div 
      className="absolute inset-y-0 left-0 z-[50] flex flex-col border-r border-slate-200/80 dark:border-slate-800 shadow-xl animate-in slide-in-from-left duration-300 transition-[width] ease-out bg-gradient-to-b from-white via-slate-50 to-white dark:from-slate-900 dark:via-slate-900 dark:to-slate-950"
      style={{ width: `${width}px`, ...style }}
    >
      {/* Resize Handle */}
      <div
        onMouseDown={onResizeStart}
        className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-blue-500/20 active:bg-blue-500/40 transition-colors z-[60]"
        title="Drag to resize"
      />

      {/* Header */}
      <div className="p-4 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-white/80 dark:bg-slate-900/70 backdrop-blur">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-600 rounded-xl shadow-sm">
            <Sparkles size={18} className="text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide">Autoflow Copilot</h2>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              {interactionMode === 'ask' ? 'Ask mode: guidance and node help' : 'Build mode: workflow generation'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onClearHistory}
            disabled={isLoading}
            className="p-2 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded-lg transition-colors text-slate-400 hover:text-rose-600 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Clear chat history from database"
          >
            <Trash2 size={18} />
          </button>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          >
            <X size={20} />
          </button>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-white/60 dark:bg-slate-900/60 backdrop-blur">
        <div className="inline-flex rounded-xl border border-slate-200 dark:border-slate-700 p-1 bg-slate-100 dark:bg-slate-800">
          <button
            onClick={() => onInteractionModeChange('ask')}
            disabled={isLoading}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors ${
              interactionMode === 'ask'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 dark:text-slate-300 hover:text-slate-700 dark:hover:text-slate-100'
            } disabled:opacity-60`}
          >
            Ask
          </button>
          <button
            onClick={() => onInteractionModeChange('build')}
            disabled={isLoading}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition-colors ${
              interactionMode === 'build'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 dark:text-slate-300 hover:text-slate-700 dark:hover:text-slate-100'
            } disabled:opacity-60`}
          >
            Build
          </button>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        onScroll={updateScrollState}
        className="relative flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.08),_transparent_52%)] dark:bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.12),_transparent_52%)]"
      >
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8">
            <div className="w-16 h-16 bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-800 rounded-2xl flex items-center justify-center mb-4">
              <Bot size={32} className="text-blue-500" />
            </div>
            <p className="text-sm text-slate-700 dark:text-slate-300 max-w-[280px]">
              {interactionMode === 'ask'
                ? '"Ask: Which nodes should I use for webhook input and Telegram output?"'
                : '"Build: Create a workflow that sends a Slack message when a new user signs up."'}
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {examplePrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleExamplePromptClick(prompt)}
                  className="rounded-full border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-800 px-3 py-1.5 text-[11px] text-slate-600 dark:text-slate-300 hover:bg-blue-50 dark:hover:bg-slate-700 transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex gap-3 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
                msg.role === 'user' ? 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-200' : 'bg-blue-600'
              }`}>
                {msg.role === 'user' ? <User size={16} /> : <Bot size={16} className="text-white" />}
              </div>
              <div className="space-y-2 group/message">
                <div className={`p-3 rounded-2xl text-sm ${
                  msg.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-tr-none shadow-md shadow-blue-500/20' 
                    : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 rounded-tl-none shadow-sm whitespace-pre-wrap leading-relaxed'
                }`}>
                  {msg.content}
                </div>
                <div className={`flex items-center gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <button
                    onClick={() => void handleCopyMessage(msg.id, msg.content)}
                    className="inline-flex items-center gap-1 rounded-full border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-900 px-2.5 py-1 text-[11px] text-slate-600 dark:text-slate-300 hover:border-blue-300 hover:text-blue-700 dark:hover:text-blue-300 transition-all opacity-0 pointer-events-none group-hover/message:opacity-100 group-hover/message:pointer-events-auto group-focus-within/message:opacity-100 group-focus-within/message:pointer-events-auto"
                    title="Copy message"
                  >
                    {copiedMessageId === msg.id ? <ClipboardCheck size={12} /> : <Copy size={12} />}
                    {copiedMessageId === msg.id ? 'Copied' : 'Copy'}
                  </button>
                  {getMessageTimeLabel(msg.timestamp) && (
                    <span className="text-[10px] text-slate-400 dark:text-slate-500">
                      {getMessageTimeLabel(msg.timestamp)}
                    </span>
                  )}
                </div>

                {msg.role === 'assistant' && msg.mode === 'clarify' && Array.isArray(msg.questions) && msg.questions.length > 0 && (
                  <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-3 flex flex-col gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">
                      Clarifications Needed
                    </span>
                    <div className="space-y-2">
                      {msg.questions.map((question, index) => (
                        <div key={`${msg.id}-${question.id}`} className="text-xs text-amber-900 dark:text-amber-100">
                          <p className="font-semibold">{index + 1}. {question.question}</p>
                          <p className="text-[11px] text-amber-700 dark:text-amber-300">{question.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* AI specific actions/workflow display */}
                {msg.role === 'assistant' && (msg as any).workflow && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-3 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
                      <Check size={14} className="font-bold" />
                      <span className="text-[11px] font-bold uppercase tracking-wider">Workflow Generated</span>
                    </div>
                    {msg.changeSummary && (
                      <p className="text-xs text-blue-800 dark:text-blue-100">
                        {msg.changeSummary}
                      </p>
                    )}
                    {(() => {
                      const workflowPayload = {
                        definition: (msg as any).workflow,
                        name: (msg as any).workflowName,
                      };
                      const signature = JSON.stringify((msg as any).workflow || {});
                      const isReviewed = reviewedWorkflowSignature === signature;

                      if (isReviewed) {
                        return (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => onAcceptReviewedWorkflow(workflowPayload)}
                              className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 active:scale-[0.98]"
                            >
                              Accept Workflow
                              <CheckCircle2 size={14} />
                            </button>
                            <button
                              onClick={() => onDiscardReviewedWorkflow(workflowPayload)}
                              className="py-2 px-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 hover:bg-slate-50 dark:hover:bg-slate-700"
                            >
                              Discard
                              <XCircle size={13} />
                            </button>
                          </div>
                        );
                      }

                      return (
                        <div className="flex items-center">
                          <button
                            onClick={() => onReviewWorkflow(workflowPayload)}
                            className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/20 active:scale-[0.98]"
                          >
                            Review on Canvas
                            <Eye size={14} />
                          </button>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex justify-start animate-in fade-in duration-300">
            <div className="flex gap-3 max-w-[85%]">
              <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center flex-shrink-0">
                <Bot size={16} className="text-white" />
              </div>
              <div className="p-3 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-tl-none shadow-sm flex items-center gap-2">
                <Loader2 size={14} className="animate-spin text-blue-500" />
                <span className="text-xs text-slate-500">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        {showScrollToBottom && (
          <button
            onClick={handleScrollToBottom}
            className="sticky bottom-2 left-full -translate-x-2 ml-auto inline-flex items-center justify-center w-9 h-9 rounded-full bg-blue-600 text-white shadow-lg shadow-blue-500/30 hover:bg-blue-700 transition-colors"
            title="Scroll to latest message"
            aria-label="Scroll to latest message"
          >
            <ChevronDown size={16} />
          </button>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white/90 dark:bg-slate-900/90 border-t border-slate-200/80 dark:border-slate-800 backdrop-blur">
        <div className="relative group">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder={inputPlaceholder}
            className="w-full bg-white dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-2xl py-3 pl-4 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-300 transition-all shadow-sm"
          />
          <button
            onClick={isLoading ? onStopGeneration : handleSend}
            disabled={isLoading ? false : !input.trim()}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-xl transition-all ${
              isLoading
                ? 'bg-rose-600 text-white shadow-lg shadow-rose-500/20 hover:scale-105'
                : input.trim()
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20 hover:scale-105'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
            }`}
            title={isLoading ? 'Stop generation' : 'Send message'}
          >
            {isLoading ? <Square size={16} /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-[10px] text-center mt-3 text-slate-400">
          {interactionMode === 'ask'
            ? 'Ask mode gives Autoflow guidance and node/parameter help.'
            : 'Build mode generates workflows that may still need manual refinement.'}
        </p>
      </div>
    </div>
  );
};

export default AIWorkflowChatPanel;
