import React, { useState } from 'react';

interface JsonTreeProps {
  data: any;
  path?: string;
  isRoot?: boolean;
}

// Grip icon (six dots)
const GripIcon = ({ className }: { className?: string }) => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" className={className}>
    <circle cx="9" cy="5"  r="1.5" fill="currentColor" />
    <circle cx="15" cy="5" r="1.5" fill="currentColor" />
    <circle cx="9"  cy="12" r="1.5" fill="currentColor" />
    <circle cx="15" cy="12" r="1.5" fill="currentColor" />
    <circle cx="9"  cy="19" r="1.5" fill="currentColor" />
    <circle cx="15" cy="19" r="1.5" fill="currentColor" />
  </svg>
);

const JsonTree: React.FC<JsonTreeProps> = ({ data, path = '', isRoot = true }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (data === null)      return <span className="text-slate-400 dark:text-slate-600 italic text-xs">null</span>;
  if (data === undefined) return <span className="text-slate-400 dark:text-slate-600 italic text-xs">undefined</span>;

  // ── Drag: KEY label → insert {{path}} placeholder ────────────────────────
  const onKeyDragStart = (e: React.DragEvent, fieldPath: string) => {
    e.stopPropagation();
    const ph = `{{${fieldPath}}}`;
    e.dataTransfer.setData('application/json-path', fieldPath);
    e.dataTransfer.setData('text/plain', ph);
    e.dataTransfer.effectAllowed = 'copy';
  };

  // ── Drag: VALUE chip → insert the raw value literally ────────────────────
  const onValueDragStart = (e: React.DragEvent, rawValue: any) => {
    e.stopPropagation();
    const str = typeof rawValue === 'string' ? rawValue : JSON.stringify(rawValue);
    e.dataTransfer.setData('application/json-value', str);
    e.dataTransfer.setData('text/plain', str);
    e.dataTransfer.effectAllowed = 'copy';
  };

  // ── Leaf primitive value ──────────────────────────────────────────────────
  if (typeof data !== 'object') {
    const displayStr = typeof data === 'string' ? `"${data}"` : String(data);

    return (
      <div
        draggable
        onDragStart={(e) => onValueDragStart(e, data)}
        title={`Drag to copy literal value`}
        className="relative inline-flex items-center group cursor-grab active:cursor-grabbing hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded px-1 transition-colors"
      >
        <span className="text-emerald-600 dark:text-emerald-400 font-mono text-xs">{displayStr}</span>
        <span className="pointer-events-none absolute -left-3 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
          <GripIcon className="text-emerald-400" />
        </span>
      </div>
    );
  }

  const isArray = Array.isArray(data);
  const keys = Object.keys(data);

  if (keys.length === 0) {
    return <span className="text-slate-400 dark:text-slate-600 font-mono text-xs">{isArray ? '[]' : '{}'}</span>;
  }

  return (
    <div className={`font-mono text-xs ${isRoot ? 'p-1' : 'ml-4'}`}>
      <div
        className="flex items-center gap-1 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 rounded select-none"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="text-slate-400 dark:text-slate-600 w-3 inline-block text-[10px]">
          {isExpanded ? '▼' : '▶'}
        </span>
        <span className="text-slate-600 dark:text-slate-400 font-bold">{isArray ? 'Array' : 'Object'}</span>
        <span className="text-slate-400 dark:text-slate-600 text-[10px]">({keys.length} items)</span>
      </div>

      {isExpanded && (
        <div className="mt-1 border-l border-slate-200 dark:border-slate-800 ml-1.5 pl-3 space-y-1">
          {keys.map((key) => {
            const currentPath = path ? `${path}.${key}` : key;
            const ph = `{{${currentPath}}}`;

            return (
              <div key={key} className="flex flex-col gap-0.5">
                <div className="flex items-start gap-1 group/row">
                  {/* KEY label — drags {{path}} placeholder */}
                  <span
                    draggable
                    onDragStart={(e) => onKeyDragStart(e, currentPath)}
                    title={`Drag key → insert ${ph}`}
                    className="relative inline-flex items-center group/key cursor-grab active:cursor-grabbing hover:bg-amber-50 dark:hover:bg-amber-900/20 px-1 rounded transition-colors"
                  >
                    <span className="pointer-events-none absolute -left-3 top-1/2 -translate-y-1/2 opacity-0 group-hover/key:opacity-100 transition-opacity">
                      <GripIcon className="text-amber-400" />
                    </span>
                    <span className="text-amber-700 dark:text-amber-500 font-bold whitespace-nowrap">
                      {key}:
                    </span>
                    {/* Tooltip badge showing what will be inserted */}
                    <span className="pointer-events-none absolute left-full ml-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/key:opacity-100 transition-opacity text-[9px] bg-amber-500 text-white px-1.5 py-0.5 rounded font-mono leading-none max-w-[220px] truncate">
                      {ph}
                    </span>
                  </span>

                  <JsonTree data={data[key]} path={currentPath} isRoot={false} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default JsonTree;
