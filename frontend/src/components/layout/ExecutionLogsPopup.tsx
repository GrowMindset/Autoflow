import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, TerminalSquare } from 'lucide-react';
import { ExecutionDetail } from '../../services/executionService';
import { useTheme } from '../../context/ThemeContext';
import ExecutionLogsPanelContent from './ExecutionLogsPanelContent';

interface ExecutionLogsPopupProps {
  isOpen: boolean;
  executionId: string | null;
  executionDetail: ExecutionDetail | null;
  onClose: () => void;
}

const ExecutionLogsPopup: React.FC<ExecutionLogsPopupProps> = ({
  isOpen,
  executionId,
  executionDetail,
  onClose,
}) => {
  const { isDark } = useTheme();
  const width = useMemo(() => Math.min(900, Math.floor(window.innerWidth * 0.9)), []);
  const height = useMemo(() => Math.min(640, Math.floor(window.innerHeight * 0.7)), []);
  const [position, setPosition] = useState<{ x: number; y: number }>({
    x: Math.max(12, window.innerWidth - width - 32),
    y: Math.max(12, window.innerHeight - height - 32),
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (!isDragging) return;

    const onMouseMove = (event: MouseEvent) => {
      const nextX = event.clientX - dragOffsetRef.current.x;
      const nextY = event.clientY - dragOffsetRef.current.y;
      const maxX = Math.max(12, window.innerWidth - width - 12);
      const maxY = Math.max(12, window.innerHeight - height - 12);
      setPosition({
        x: Math.min(maxX, Math.max(12, nextX)),
        y: Math.min(maxY, Math.max(12, nextY)),
      });
    };

    const onMouseUp = () => {
      setIsDragging(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging, width, height]);

  useEffect(() => {
    if (!isOpen) return;
    const maxX = Math.max(12, window.innerWidth - width - 12);
    const maxY = Math.max(12, window.innerHeight - height - 12);
    setPosition((prev) => ({
      x: Math.min(maxX, Math.max(12, prev.x)),
      y: Math.min(maxY, Math.max(12, prev.y)),
    }));
  }, [isOpen, width, height]);

  useEffect(() => {
    return () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, []);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[70] pointer-events-none">
      <div
        className={`pointer-events-auto absolute rounded-2xl border shadow-[0_30px_80px_rgba(2,6,23,0.35)] overflow-hidden ${
          isDark
            ? 'border-slate-700 bg-slate-950 text-slate-100'
            : 'border-slate-200 bg-white text-slate-900'
        }`}
        style={{
          left: position.x,
          top: position.y,
          width,
          height,
        }}
      >
        <div
          className={`h-12 px-4 border-b flex items-center justify-between ${
            isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-slate-50'
          }`}
          onMouseDown={(event) => {
            const rect = event.currentTarget.parentElement?.getBoundingClientRect();
            if (!rect) return;
            dragOffsetRef.current = {
              x: event.clientX - rect.left,
              y: event.clientY - rect.top,
            };
            setIsDragging(true);
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'move';
          }}
          style={{ cursor: isDragging ? 'move' : 'grab' }}
        >
          <div className="flex items-center gap-2">
            <TerminalSquare
              size={16}
              className={isDark ? 'text-cyan-300' : 'text-sky-600'}
            />
            <span className="text-[11px] font-black uppercase tracking-[0.2em]">
              Pop Logs
            </span>
            <span className={`text-[10px] font-mono ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {executionId ? `${executionId.slice(0, 8)}...` : 'No execution'}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            onMouseDown={(event) => event.stopPropagation()}
            className={`rounded-md p-1.5 transition ${
              isDark ? 'hover:bg-slate-800 text-slate-300' : 'hover:bg-slate-200 text-slate-600'
            }`}
            title="Close pop logs"
          >
            <X size={16} />
          </button>
        </div>

        <div className={`h-[calc(100%-48px)] overflow-auto p-4 ${isDark ? 'bg-slate-950' : 'bg-slate-100/80'}`}>
          <ExecutionLogsPanelContent executionDetail={executionDetail} />
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default ExecutionLogsPopup;
