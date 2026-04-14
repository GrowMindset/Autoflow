import React, { useMemo } from 'react';
import { ChevronUp, GripHorizontal, TerminalSquare } from 'lucide-react';
import { ExecutionDetail } from '../../services/executionService';
import { useTheme } from '../../context/ThemeContext';
import ExecutionLogsPanelContent from './ExecutionLogsPanelContent';

interface ExecutionLogsFooterProps {
  executionDetail: ExecutionDetail | null;
  executionId: string | null;
  isExpanded: boolean;
  panelHeight: number;
  onToggle: () => void;
  onResizeStart: (event: React.MouseEvent<HTMLDivElement>) => void;
  isPopoutOpen: boolean;
  onTogglePopout: () => void;
}

const COLLAPSED_HEIGHT = 52;

const toneByStatus = (status: string) => {
  switch (status) {
    case 'SUCCEEDED':
      return {
        dot: 'bg-emerald-500',
        text: 'text-emerald-500 dark:text-emerald-400',
        badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
      };
    case 'FAILED':
      return {
        dot: 'bg-rose-500',
        text: 'text-rose-500 dark:text-rose-400',
        badge: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
      };
    case 'RUNNING':
      return {
        dot: 'bg-amber-500',
        text: 'text-amber-500 dark:text-amber-300',
        badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200',
      };
    default:
      return {
        dot: 'bg-slate-400 dark:bg-slate-500',
        text: 'text-slate-500 dark:text-slate-400',
        badge: 'bg-slate-100 text-slate-700 dark:bg-slate-700/60 dark:text-slate-200',
      };
  }
};

const ExecutionLogsFooter: React.FC<ExecutionLogsFooterProps> = ({
  executionDetail,
  executionId,
  isExpanded,
  panelHeight,
  onToggle,
  onResizeStart,
  isPopoutOpen,
  onTogglePopout,
}) => {
  const { isDark } = useTheme();

  const sortedNodeResults = useMemo(
    () =>
      [...(executionDetail?.node_results ?? [])].sort((left, right) => {
        const leftValue = left.started_at ?? left.finished_at ?? '';
        const rightValue = right.started_at ?? right.finished_at ?? '';
        if (leftValue && rightValue) {
          return new Date(leftValue).getTime() - new Date(rightValue).getTime();
        }
        if (leftValue) return -1;
        if (rightValue) return 1;
        return 0;
      }),
    [executionDetail],
  );

  const executedNodesCount = sortedNodeResults.filter(
    (node) => node.status !== 'PENDING',
  ).length;

  return (
    <div
      className={`absolute bottom-0 left-0 right-0 z-30 overflow-hidden border-t shadow-[0_-16px_40px_rgba(15,23,42,0.16)] transition-colors duration-300 ${
        isDark
          ? 'border-slate-800 bg-slate-950 text-slate-100'
          : 'border-slate-200 bg-white text-slate-900'
      }`}
      style={{ height: isExpanded ? panelHeight : COLLAPSED_HEIGHT }}
    >
      {isExpanded && (
        <div className="absolute left-0 right-0 top-0 z-20 flex justify-center">
          <div
            className={`mt-1 flex h-5 w-24 cursor-row-resize items-center justify-center rounded-full border transition-colors ${
              isDark
                ? 'border-slate-700 bg-slate-900/95 text-slate-400 hover:text-slate-200'
                : 'border-slate-200 bg-white/95 text-slate-400 hover:text-slate-700'
            }`}
            onMouseDown={onResizeStart}
            title="Drag to resize logs"
          >
            <GripHorizontal size={18} />
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={onToggle}
        className={`relative flex h-[52px] w-full items-center justify-between border-b px-6 text-left transition-colors ${
          isDark
            ? 'border-slate-800 bg-slate-900'
            : 'border-slate-200 bg-slate-50'
        }`}
      >
        <div className="flex items-center gap-3">
          <TerminalSquare
            size={18}
            className={isDark ? 'text-cyan-300' : 'text-sky-600'}
          />
          <div className="flex flex-col">
            <span
              className={`text-[11px] font-black uppercase tracking-[0.24em] ${
                isDark ? 'text-slate-200' : 'text-slate-800'
              }`}
            >
              Logs
            </span>
            <span
              className={`text-[10px] font-mono ${
                isDark ? 'text-slate-400' : 'text-slate-500'
              }`}
            >
              {executionId ? `Current execution: ${executionId.slice(0, 8)}...` : 'No execution started yet'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 text-[10px] font-mono">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onTogglePopout();
            }}
            className={`rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-[0.18em] transition ${
              isDark
                ? 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-100'
            }`}
          >
            {isPopoutOpen ? 'Hide Pop' : 'Pop Logs'}
          </button>
          {executionDetail ? (
            <>
              <span className={`${toneByStatus(executionDetail.status).text} font-bold`}>
                {executionDetail.status}
              </span>
              <span className={isDark ? 'text-slate-600' : 'text-slate-300'}>|</span>
              <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                {executedNodesCount} node events
              </span>
            </>
          ) : (
            <span className={isDark ? 'text-slate-500' : 'text-slate-400'}>
              Waiting for workflow run...
            </span>
          )}
        </div>
      </button>

      {isExpanded && (
        <div
          className={`h-[calc(100%-52px)] overflow-auto px-5 py-4 transition-colors ${
            isDark ? 'bg-slate-950' : 'bg-slate-100/80'
          }`}
        >
          <ExecutionLogsPanelContent executionDetail={executionDetail} />
        </div>
      )}
    </div>
  );
};

export default ExecutionLogsFooter;
