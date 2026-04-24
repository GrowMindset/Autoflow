import React, { useMemo, useState } from 'react';
import JsonTree from './JsonTree';

type DataViewMode = 'json' | 'table';

interface FlatRow {
  path: string;
  value: string;
  rawValue: unknown;
}

interface DataViewProps {
  data: unknown;
  emptyMessage?: string;
  initialMode?: DataViewMode;
}

const MAX_CELL_STRING_LENGTH = 240;

const truncateMiddle = (value: string, maxLength = MAX_CELL_STRING_LENGTH): string => {
  if (value.length <= maxLength) return value;
  const edgeLength = Math.floor((maxLength - 15) / 2);
  return `${value.slice(0, edgeLength)} ... ${value.slice(-edgeLength)} (${value.length.toLocaleString()} chars)`;
};

const stringifyValue = (value: unknown): string => {
  if (value === undefined) return 'undefined';
  if (typeof value === 'string') return value;
  if (value === null || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return '[unserializable]';
  }
};

const flattenValue = (value: unknown, path: string, rows: FlatRow[]): void => {
  if (value === null || value === undefined || typeof value !== 'object') {
    rows.push({
      path,
      value: stringifyValue(value),
      rawValue: value,
    });
    return;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      rows.push({
        path,
        value: '[]',
        rawValue: value,
      });
      return;
    }

    value.forEach((item, index) => {
      flattenValue(item, `${path}[${index}]`, rows);
    });
    return;
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) {
    rows.push({
      path,
      value: '{}',
      rawValue: value,
    });
    return;
  }

  entries.forEach(([key, nestedValue]) => {
    const nextPath = path === 'root' ? key : `${path}.${key}`;
    flattenValue(nestedValue, nextPath, rows);
  });
};

const DataView: React.FC<DataViewProps> = ({
  data,
  emptyMessage = 'No data available',
  initialMode = 'json',
}) => {
  const [mode, setMode] = useState<DataViewMode>(initialMode);

  const normalizePathForTemplate = (path: string): string => {
    if (path.startsWith('root.')) return path.slice(5);
    if (path.startsWith('root[')) return path.slice(4);
    return path;
  };

  const handlePathDragStart = (event: React.DragEvent, rowPath: string) => {
    const normalizedPath = normalizePathForTemplate(rowPath);
    const template = `{{${normalizedPath}}}`;
    event.dataTransfer.setData('application/json-path', normalizedPath);
    event.dataTransfer.setData('text/plain', template);
    event.dataTransfer.effectAllowed = 'copy';
  };

  const handleValueDragStart = (event: React.DragEvent, rawValue: unknown) => {
    const literal =
      typeof rawValue === 'string'
        ? rawValue
        : JSON.stringify(rawValue) ?? String(rawValue);
    event.dataTransfer.setData('application/json-value', literal);
    event.dataTransfer.setData('text/plain', literal);
    event.dataTransfer.effectAllowed = 'copy';
  };

  const rows = useMemo<FlatRow[]>(() => {
    if (data === null || data === undefined) {
      return [];
    }
    const nextRows: FlatRow[] = [];
    flattenValue(data, 'root', nextRows);
    return nextRows;
  }, [data]);

  if (data === null || data === undefined) {
    return (
      <span className="text-[10px] text-slate-300 dark:text-slate-600 italic px-2 py-4 block">
        {emptyMessage}
      </span>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-1">
        <span className="mr-2 text-[10px] text-slate-400 dark:text-slate-500">
          Drag `Path` for variable, `Value` for literal
        </span>
        <button
          type="button"
          onClick={() => setMode('json')}
          className={`rounded-md px-2 py-1 text-[10px] font-black uppercase tracking-widest transition-colors ${
            mode === 'json'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'bg-slate-100 text-slate-500 hover:text-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          JSON
        </button>
        <button
          type="button"
          onClick={() => setMode('table')}
          className={`rounded-md px-2 py-1 text-[10px] font-black uppercase tracking-widest transition-colors ${
            mode === 'table'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'bg-slate-100 text-slate-500 hover:text-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          Table
        </button>
      </div>

      {mode === 'json' ? (
        <JsonTree data={data} />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
          <div className="max-h-[360px] overflow-auto">
            <table className="w-full min-w-[760px] table-fixed border-collapse text-xs">
              <colgroup>
                <col className="w-[42%]" />
                <col className="w-[58%]" />
              </colgroup>
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="border-b border-r border-slate-200 dark:border-slate-700 px-3 py-2 text-left font-black uppercase tracking-widest">
                    Path
                  </th>
                  <th className="border-b border-slate-200 dark:border-slate-700 px-3 py-2 text-left font-black uppercase tracking-widest">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={`${row.path}_${index}`}
                    className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50"
                  >
                    <td className="border-b border-r border-slate-100 dark:border-slate-800 px-3 py-2 font-mono text-[11px] text-slate-700 dark:text-slate-300 align-top">
                      <span
                        draggable
                        onDragStart={(event) => handlePathDragStart(event, row.path)}
                        title={`Drag variable {{${normalizePathForTemplate(row.path)}}}`}
                        className="inline-flex max-w-full cursor-grab items-center rounded px-1.5 py-0.5 hover:bg-amber-50 active:cursor-grabbing dark:hover:bg-amber-900/20"
                      >
                        <span className="truncate whitespace-nowrap">{row.path}</span>
                      </span>
                    </td>
                    <td className="border-b border-slate-100 dark:border-slate-800 px-3 py-2 font-mono text-[11px] text-emerald-600 dark:text-emerald-400 align-top">
                      <span
                        draggable
                        onDragStart={(event) => handleValueDragStart(event, row.rawValue)}
                        title="Drag to copy literal value"
                        className="inline-flex max-w-full cursor-grab items-center rounded px-1.5 py-0.5 hover:bg-emerald-50 active:cursor-grabbing dark:hover:bg-emerald-900/20"
                      >
                        <span className="truncate whitespace-nowrap">{truncateMiddle(row.value)}</span>
                      </span>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={2}
                      className="px-3 py-4 text-center text-[11px] italic text-slate-400 dark:text-slate-500"
                    >
                      No rows available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataView;
