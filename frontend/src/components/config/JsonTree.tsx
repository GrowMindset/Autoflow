import React, { useState } from 'react';

interface JsonTreeProps {
  data: any;
  path?: string;
  isRoot?: boolean;
}

const JsonTree: React.FC<JsonTreeProps> = ({ data, path = '', isRoot = true }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (data === null) return <span className="text-slate-400 dark:text-slate-600 italic text-xs">null</span>;
  if (data === undefined) return <span className="text-slate-400 dark:text-slate-600 italic text-xs">undefined</span>;

  const placeholder = `{{${path}}}`;

  const onDragStart = (e: React.DragEvent, fieldPath: string) => {
    const ph = `{{${fieldPath}}}`;
    e.dataTransfer.setData('application/json-path', fieldPath);
    e.dataTransfer.setData('text/plain', ph);
    e.dataTransfer.effectAllowed = 'copy';
  };

  if (typeof data !== 'object') {
    return (
      <div
        draggable
        onDragStart={(e) => onDragStart(e, path)}
        title={`Drag to insert ${placeholder}`}
        className="inline-flex items-center gap-2 group cursor-grab active:cursor-grabbing hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded px-1 transition-colors"
      >
        <span className="text-blue-600 dark:text-blue-400 font-mono text-xs">
          {typeof data === 'string' ? `"${data}"` : String(data)}
        </span>
        <span className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
          {/* drag icon */}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-400 dark:text-blue-500">
            <circle cx="9" cy="5" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="15" cy="5" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="9" cy="12" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="15" cy="12" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="9" cy="19" r="1.5" fill="currentColor" stroke="none"/>
            <circle cx="15" cy="19" r="1.5" fill="currentColor" stroke="none"/>
          </svg>
          <span className="text-[9px] bg-blue-500 text-white px-1.5 py-0.5 rounded font-mono leading-none">
            {placeholder}
          </span>
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
    <div className={`font-mono text-xs ${isRoot ? 'p-2' : 'ml-4'}`}>
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
            const childIsLeaf = typeof data[key] !== 'object' || data[key] === null;
            return (
              <div key={key} className="flex flex-col gap-0.5">
                <div className="flex items-start gap-1 group/row">
                  <span
                    draggable={childIsLeaf}
                    onDragStart={(e) => onDragStart(e, currentPath)}
                    title={childIsLeaf ? `Drag to insert {{${currentPath}}}` : undefined}
                    className={`text-amber-700 dark:text-amber-500 font-bold whitespace-nowrap px-1 rounded transition-colors ${
                      childIsLeaf
                        ? 'cursor-grab active:cursor-grabbing hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-900 dark:hover:text-amber-300'
                        : 'cursor-default'
                    }`}
                  >
                    {key}:
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
