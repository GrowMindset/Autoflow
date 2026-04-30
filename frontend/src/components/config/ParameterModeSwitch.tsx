import React from 'react';
import clsx from 'clsx';
import type { ParameterMode } from './ConfigForm';

interface ParameterModeSwitchProps {
  mode: ParameterMode;
  onModeChange: (mode: ParameterMode) => void;
  className?: string;
}

const OPTIONS: Array<{ label: string; value: ParameterMode }> = [
  { label: 'Fixed', value: 'fixed' },
  { label: 'Expression', value: 'expression' },
];

const ParameterModeSwitch: React.FC<ParameterModeSwitchProps> = ({
  mode,
  onModeChange,
  className,
}) => {
  return (
    <div
      className={clsx(
        'inline-flex items-center rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-0.5',
        className,
      )}
      role="tablist"
      aria-label="Parameter mode"
    >
      {OPTIONS.map((option) => {
        const active = mode === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onModeChange(option.value)}
            className={clsx(
              'rounded-full px-2.5 py-0.5 text-[10px] font-semibold transition-colors',
              active
                ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
};

export default ParameterModeSwitch;
