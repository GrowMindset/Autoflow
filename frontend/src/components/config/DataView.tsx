import React, { useMemo, useState } from 'react';
import JsonTree from './JsonTree';

type DataViewMode = 'schema' | 'table' | 'json';

interface FlatRow {
  path: string;
  value: string;
  rawValue: unknown;
}

interface SchemaRow {
  path: string;
  depth: number;
  value: string;
  rawValue: unknown;
  isContainer: boolean;
}

interface DataViewProps {
  data: unknown;
  emptyMessage?: string;
  initialMode?: DataViewMode;
}

const MAX_CELL_STRING_LENGTH = 240;
const MAX_SCHEMA_ARRAY_ITEMS = 60;

const truncateMiddle = (value: string, maxLength = MAX_CELL_STRING_LENGTH): string => {
  if (value.length <= maxLength) return value;
  const edgeLength = Math.floor((maxLength - 15) / 2);
  return `${value.slice(0, edgeLength)} ... ${value.slice(-edgeLength)} (${value.length.toLocaleString()} chars)`;
};

const normalizePathForTemplate = (path: string): string => {
  if (path.startsWith('root.')) return path.slice(5);
  if (path.startsWith('root[')) return path.slice(4);
  return path;
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

const formatSchemaValue = (value: unknown): string => {
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    return `[${value.length} items]`;
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>);
    if (keys.length === 0) return '{}';
    return `{${keys.length} fields}`;
  }
  return stringifyValue(value);
};

const buildSchemaPath = (segments: string[]): string => {
  if (segments.length === 0) return 'root';
  return `root${segments.map((segment) => (segment === '[]' ? '[]' : `.${segment}`)).join('')}`;
};

interface SchemaAccumulator {
  path: string;
  depth: number;
  order: number;
  values: Set<string>;
  rawValue: unknown;
  isContainer: boolean;
}

const registerSchemaNode = (
  registry: Map<string, SchemaAccumulator>,
  path: string,
  depth: number,
  value: unknown,
  isContainer: boolean,
  orderRef: { value: number },
) => {
  const valueLabel = formatSchemaValue(value);
  const existing = registry.get(path);
  if (!existing) {
    registry.set(path, {
      path,
      depth,
      order: orderRef.value++,
      values: new Set([valueLabel]),
      rawValue: value,
      isContainer,
    });
    return;
  }

  if (existing.values.size < 3) {
    existing.values.add(valueLabel);
  }
  existing.isContainer = existing.isContainer || isContainer;
};

const walkSchema = (
  value: unknown,
  segments: string[],
  registry: Map<string, SchemaAccumulator>,
  orderRef: { value: number },
  visited: WeakSet<object>,
) => {
  const path = buildSchemaPath(segments);
  const isContainer = Boolean(value) && typeof value === 'object';

  registerSchemaNode(
    registry,
    path,
    segments.length,
    value,
    isContainer,
    orderRef,
  );

  if (value === null || value === undefined || typeof value !== 'object') {
    return;
  }

  if (visited.has(value)) {
    return;
  }
  visited.add(value);

  if (Array.isArray(value)) {
    value.slice(0, MAX_SCHEMA_ARRAY_ITEMS).forEach((item) => {
      walkSchema(item, [...segments, '[]'], registry, orderRef, visited);
    });
    return;
  }

  Object.entries(value as Record<string, unknown>).forEach(([key, nestedValue]) => {
    walkSchema(nestedValue, [...segments, key], registry, orderRef, visited);
  });
};

const DataView: React.FC<DataViewProps> = ({
  data,
  emptyMessage = 'No data available',
  initialMode = 'json',
}) => {
  const [mode, setMode] = useState<DataViewMode>(initialMode);

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

  const schemaRows = useMemo<SchemaRow[]>(() => {
    if (data === null || data === undefined) {
      return [];
    }
    const registry = new Map<string, SchemaAccumulator>();
    const orderRef = { value: 0 };
    const visited = new WeakSet<object>();

    walkSchema(data, [], registry, orderRef, visited);

    return Array.from(registry.values())
      .sort((a, b) => a.order - b.order)
      .map((row) => ({
        path: row.path,
        depth: row.depth,
        value: Array.from(row.values)[0] || '',
        rawValue: row.rawValue,
        isContainer: row.isContainer,
      }));
  }, [data]);

  if (data === null || data === undefined) {
    return (
      <span className="text-[10px] text-slate-300 dark:text-slate-600 italic px-2 py-4 block">
        {emptyMessage}
      </span>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] text-slate-400 dark:text-slate-500">
          {mode === 'json'
            ? 'Drag a key to insert {{path}}, or drag a value to insert literals'
            : mode === 'table'
              ? 'Drag `Path` for variable, `Value` for literal'
              : 'Drag `Field` for variable, `Value` for literal'}
        </span>
        <div className="inline-flex items-center rounded-xl border border-slate-200 bg-slate-100/80 p-1 dark:border-slate-700 dark:bg-slate-800/70">
          {(['schema', 'table', 'json'] as const).map((view) => (
            <button
              key={view}
              type="button"
              onClick={() => setMode(view)}
              className={`rounded-lg px-2.5 py-1 text-[10px] font-black uppercase tracking-wider transition-colors ${
                mode === view
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-100 dark:text-slate-900'
                  : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {view}
            </button>
          ))}
        </div>
      </div>

      {mode === 'json' && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <div className="max-h-[400px] overflow-auto p-2">
            <JsonTree data={data} />
          </div>
        </div>
      )}

      {mode === 'table' && (
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

      {mode === 'schema' && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <div className="max-h-[420px] overflow-auto p-2.5">
            <div className="space-y-1.5">
              {schemaRows.map((row, index) => {
                const normalizedPath = normalizePathForTemplate(row.path);
                const isRootRow = row.path === 'root';
                const containerLabel = Array.isArray(row.rawValue)
                  ? 'array'
                  : row.isContainer
                    ? 'object'
                    : null;

                return (
                  <div
                    key={`${row.path}_${index}`}
                    className="rounded-xl border border-slate-200/90 bg-gradient-to-r from-white to-slate-50/70 px-2.5 py-2 shadow-sm dark:border-slate-700 dark:from-slate-900 dark:to-slate-800/60"
                  >
                    <div
                      className="flex min-w-0 items-start gap-2"
                      style={{ paddingLeft: `${row.depth * 14}px` }}
                    >
                      <span className="mt-1 text-[10px] text-slate-400 dark:text-slate-600">
                        {row.isContainer ? '▾' : '•'}
                      </span>
                      <div className="min-w-0 flex-1 space-y-1.5">
                        <div className="flex min-w-0 items-center gap-1.5">
                          {isRootRow ? (
                            <span className="inline-flex rounded-md border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                              root
                            </span>
                          ) : (
                            <span
                              draggable
                              onDragStart={(event) => handlePathDragStart(event, row.path)}
                              title={`Drag variable {{${normalizedPath}}}`}
                              className="inline-flex max-w-full cursor-grab items-center rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-700 hover:bg-amber-100 active:cursor-grabbing dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300"
                            >
                              <span className="truncate whitespace-nowrap">{normalizedPath}</span>
                            </span>
                          )}
                          {containerLabel && (
                            <span className="inline-flex rounded-md border border-sky-200 bg-sky-50 px-1.5 py-0.5 font-mono text-[9px] font-black uppercase tracking-wider text-sky-700 dark:border-sky-900/60 dark:bg-sky-900/25 dark:text-sky-300">
                              {containerLabel}
                            </span>
                          )}
                        </div>
                        <div>
                          <span
                            draggable
                            onDragStart={(event) => handleValueDragStart(event, row.rawValue)}
                            title="Drag to copy literal value"
                            className="inline-flex max-w-full cursor-grab items-center rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-700 hover:bg-emerald-100 active:cursor-grabbing dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-300"
                          >
                            <span className="truncate whitespace-nowrap">{truncateMiddle(row.value)}</span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
              {schemaRows.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] italic text-slate-400 dark:border-slate-700 dark:text-slate-500">
                  Schema could not be inferred from this payload
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataView;
