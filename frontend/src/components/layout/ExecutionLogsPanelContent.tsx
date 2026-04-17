import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ExecutionDetail } from '../../services/executionService';
import { useTheme } from '../../context/ThemeContext';
import { formatTimeInAppTimezone } from '../../utils/dateTime';

interface ExecutionLogsPanelContentProps {
  executionDetail: ExecutionDetail | null;
}

const formatTimestamp = (value: string | null) => {
  return formatTimeInAppTimezone(value);
};

const formatJson = (value: unknown) => {
  if (value === null || value === undefined) {
    return 'null';
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const toneByStatus = (status: string) => {
  switch (status) {
    case 'SUCCEEDED':
      return {
        dot: 'bg-emerald-500',
        badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
      };
    case 'FAILED':
      return {
        dot: 'bg-rose-500',
        badge: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
      };
    case 'RUNNING':
      return {
        dot: 'bg-amber-500',
        badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200',
      };
    default:
      return {
        dot: 'bg-slate-400 dark:bg-slate-500',
        badge: 'bg-slate-100 text-slate-700 dark:bg-slate-700/60 dark:text-slate-200',
      };
  }
};

const ExecutionLogsPanelContent: React.FC<ExecutionLogsPanelContentProps> = ({
  executionDetail,
}) => {
  const { isDark } = useTheme();
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

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

  if (!executionDetail) {
    return (
      <div
        className={`rounded-2xl border border-dashed px-4 py-6 text-sm ${
          isDark
            ? 'border-slate-800 bg-slate-900 text-slate-500'
            : 'border-slate-300 bg-white text-slate-500'
        }`}
      >
        Execute the workflow to open a fresh log session for that run.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        className={`rounded-2xl border px-4 py-3 ${
          isDark
            ? 'border-slate-800 bg-slate-900'
            : 'border-slate-200 bg-white'
        }`}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`text-[11px] font-black uppercase tracking-[0.2em] ${
              isDark ? 'text-slate-400' : 'text-slate-500'
            }`}
          >
            Current Run
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.18em] ${
              toneByStatus(executionDetail.status).badge
            }`}
          >
            {executionDetail.status}
          </span>
          <span
            className={`text-[11px] font-mono ${
              isDark ? 'text-slate-500' : 'text-slate-400'
            }`}
          >
            {executedNodesCount} node events
          </span>
        </div>
        <div
          className={`mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px] font-mono ${
            isDark ? 'text-slate-300' : 'text-slate-700'
          }`}
        >
          <span><span className={isDark ? 'text-slate-500' : 'text-slate-400'}>workflow</span> {executionDetail.workflow_id.slice(0, 8)}...</span>
          <span><span className={isDark ? 'text-slate-500' : 'text-slate-400'}>execution</span> {executionDetail.id.slice(0, 8)}...</span>
          <span><span className={isDark ? 'text-slate-500' : 'text-slate-400'}>trigger</span> {executionDetail.triggered_by}</span>
        </div>
        {executionDetail.error_message && (
          <div
            className={`mt-3 rounded-xl border px-3 py-2 text-sm ${
              isDark
                ? 'border-rose-900/50 bg-rose-950/30 text-rose-300'
                : 'border-rose-200 bg-rose-50 text-rose-700'
            }`}
          >
            {executionDetail.error_message}
          </div>
        )}
      </div>

      {sortedNodeResults.length > 0 ? (
        sortedNodeResults.map((nodeResult) => {
          const rowExpanded = Boolean(expandedRows[nodeResult.node_id]);
          const tone = toneByStatus(nodeResult.status);

          return (
            <div
              key={nodeResult.node_id}
              className={`rounded-2xl border transition-colors ${
                isDark
                  ? 'border-slate-800 bg-slate-900'
                  : 'border-slate-200 bg-white'
              }`}
            >
              <button
                type="button"
                onClick={() =>
                  setExpandedRows((prev) => ({
                    ...prev,
                    [nodeResult.node_id]: !prev[nodeResult.node_id],
                  }))
                }
                className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className={`h-2.5 w-2.5 rounded-full ${tone.dot}`} />
                  <span
                    className={`text-[12px] font-mono ${
                      isDark ? 'text-slate-300' : 'text-slate-700'
                    }`}
                  >
                    [{formatTimestamp(nodeResult.started_at ?? nodeResult.finished_at)}]
                  </span>
                  <span
                    className={`truncate text-sm font-bold ${
                      isDark ? 'text-slate-100' : 'text-slate-900'
                    }`}
                  >
                    {nodeResult.node_id}
                  </span>
                  <span
                    className={`truncate text-xs ${
                      isDark ? 'text-slate-500' : 'text-slate-400'
                    }`}
                  >
                    ({nodeResult.node_type})
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.18em] ${
                      tone.badge
                    }`}
                  >
                    {nodeResult.status}
                  </span>
                  {rowExpanded ? (
                    <ChevronDown size={18} className={isDark ? 'text-slate-400' : 'text-slate-500'} />
                  ) : (
                    <ChevronRight size={18} className={isDark ? 'text-slate-400' : 'text-slate-500'} />
                  )}
                </div>
              </button>

              {rowExpanded && (
                <div
                  className={`border-t px-4 py-4 ${
                    isDark
                      ? 'border-slate-800'
                      : 'border-slate-200'
                  }`}
                >
                  <div className="grid gap-4 lg:grid-cols-2">
                    <div>
                      <div
                        className={`mb-2 text-[11px] font-black uppercase tracking-[0.22em] ${
                          isDark ? 'text-slate-500' : 'text-slate-500'
                        }`}
                      >
                        Input
                      </div>
                      <pre
                        className={`overflow-auto rounded-xl border px-3 py-2 text-[12px] font-mono leading-6 ${
                          isDark
                            ? 'border-slate-800 bg-slate-950 text-slate-300'
                            : 'border-slate-200 bg-slate-50 text-slate-700'
                        }`}
                      >
                        {formatJson(nodeResult.input_data)}
                      </pre>
                    </div>

                    <div>
                      <div
                        className={`mb-2 text-[11px] font-black uppercase tracking-[0.22em] ${
                          isDark ? 'text-slate-500' : 'text-slate-500'
                        }`}
                      >
                        Output
                      </div>
                      <pre
                        className={`overflow-auto rounded-xl border px-3 py-2 text-[12px] font-mono leading-6 ${
                          isDark
                            ? 'border-slate-800 bg-slate-950 text-slate-300'
                            : 'border-slate-200 bg-slate-50 text-slate-700'
                        }`}
                      >
                        {formatJson(nodeResult.output_data)}
                      </pre>
                    </div>
                  </div>

                  {nodeResult.error_message && (
                    <div
                      className={`mt-4 rounded-xl border px-3 py-2 text-sm ${
                        isDark
                          ? 'border-rose-900/50 bg-rose-950/30 text-rose-300'
                          : 'border-rose-200 bg-rose-50 text-rose-700'
                      }`}
                    >
                      {nodeResult.error_message}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })
      ) : (
        <div
          className={`rounded-2xl border border-dashed px-4 py-6 text-sm ${
            isDark
              ? 'border-slate-800 bg-slate-900 text-slate-500'
              : 'border-slate-300 bg-white text-slate-500'
          }`}
        >
          No node results yet. Start a workflow run to stream the current execution here.
        </div>
      )}
    </div>
  );
};

export default ExecutionLogsPanelContent;
