import React, { useState } from 'react';

interface JsonTreeProps {
  data: any;
  path?: string;
  isRoot?: boolean;
}

const JsonTree: React.FC<JsonTreeProps> = ({ data, path = '', isRoot = true }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const toggleExpand = () => setIsExpanded(!isExpanded);

  if (data === null) return <span className="text-slate-400 italic">null</span>;
  if (data === undefined) return <span className="text-slate-400 italic">undefined</span>;

  const onDragStart = (e: React.DragEvent, fieldPath: string) => {
    e.dataTransfer.setData('application/json-path', fieldPath);
    // Add visual feedback
    e.dataTransfer.effectAllowed = 'copy';
  };

  if (typeof data !== 'object') {
    return (
      <div
        draggable
        onDragStart={(e) => onDragStart(e, path)}
        className="inline-flex items-center gap-2 group cursor-grab active:cursor-grabbing hover:bg-slate-100 rounded px-1 transition-colors"
      >
        <span className="text-blue-600 font-mono text-xs">
          {typeof data === 'string' ? `"${data}"` : String(data)}
        </span>
        <div className="opacity-0 group-hover:opacity-100 text-[10px] bg-slate-800 text-white px-1.5 py-0.5 rounded leading-none transition-opacity">
          Drag to map
        </div>
      </div>
    );
  }

  const isArray = Array.isArray(data);
  const keys = Object.keys(data);

  if (keys.length === 0) {
    return <span className="text-slate-400 font-mono text-xs">{isArray ? '[]' : '{}'}</span>;
  }

  return (
    <div className={`font-mono text-xs ${isRoot ? 'p-2' : 'ml-4'}`}>
      <div className="flex items-center gap-1 cursor-pointer hover:bg-slate-50 rounded" onClick={toggleExpand}>
        <span className="text-slate-400 w-3 inline-block">
          {isExpanded ? '▼' : '▶'}
        </span>
        <span className="text-slate-600 font-bold">{isArray ? 'Array' : 'Object'}</span>
        <span className="text-slate-400 text-[10px]">({keys.length} items)</span>
      </div>

      {isExpanded && (
        <div className="mt-1 border-l border-slate-200 ml-1.5 pl-3 space-y-1">
          {keys.map((key) => {
            const currentPath = path ? `${path}.${key}` : key;
            return (
              <div key={key} className="flex flex-col gap-0.5">
                <div className="flex items-start gap-1">
                  <span className="text-amber-700 font-bold whitespace-nowrap">{key}:</span>
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
