import React from 'react';

export type FormFieldValue = string | number | boolean | string[];
export type FormValues = Record<string, FormFieldValue>;
export type FormErrors = Record<string, string>;

export type FormOption = {
  label?: string;
  value?: string;
};

export type FormField = {
  id?: string;
  name?: string;
  label?: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
  options?: FormOption[];
  layout?: 'inline' | 'stacked';
  default_checked?: boolean;
  min_date?: string;
  max_date?: string;
  min_time?: string;
  max_time?: string;
  min_datetime?: string;
  max_datetime?: string;
  default_country_code?: string;
  max_stars?: number;
};

const inputClass =
  'w-full rounded-2xl border bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white';
const errorClass = 'border-red-400 focus:border-red-500';
const normalClass = 'border-slate-200';

export const getFormFieldKey = (field: FormField, index: number): string =>
  String(field?.name || field?.id || `field_${index + 1}`).trim();

export const readFormValuesFromElement = (
  form: HTMLFormElement,
  fields: FormField[],
  currentValues: FormValues,
): FormValues => {
  const nextValues: FormValues = { ...currentValues };
  const elements = Array.from(form.elements) as Array<
    HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  >;

  fields.forEach((field, index) => {
    const key = getFormFieldKey(field, index);
    const matchingElements = elements.filter((element) => element.name === key);
    if (matchingElements.length === 0) return;

    if (field.type === 'checkbox') {
      nextValues[key] = Boolean((matchingElements[0] as HTMLInputElement).checked);
      return;
    }

    if (field.type === 'checkbox_group') {
      nextValues[key] = matchingElements
        .filter((element) => (element as HTMLInputElement).checked)
        .map((element) => String((element as HTMLInputElement).value));
      return;
    }

    if (field.type === 'radio') {
      const checked = matchingElements.find((element) => (element as HTMLInputElement).checked);
      nextValues[key] = checked ? String((checked as HTMLInputElement).value) : '';
      return;
    }

    nextValues[key] = String(matchingElements[0].value ?? '');
  });

  return nextValues;
};

export const initializeFormValues = (fields: FormField[]): FormValues => {
  const values: FormValues = {};
  fields.forEach((field, index) => {
    const key = getFormFieldKey(field, index);
    if (field.type === 'checkbox') {
      values[key] = Boolean(field.default_checked);
    } else if (field.type === 'checkbox_group') {
      values[key] = [];
    } else {
      values[key] = '';
    }
  });
  return values;
};

export const isValidUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

export const validateFormValues = (fields: FormField[], values: FormValues): FormErrors => {
  const errors: FormErrors = {};

  fields.forEach((field, index) => {
    const key = getFormFieldKey(field, index);
    const label = field.label || key;
    const value = values[key];
    const hasValue = Array.isArray(value)
      ? value.length > 0
      : value !== undefined && value !== null && value !== '';

    if (field.required && !hasValue) {
      errors[key] = `${label} is required.`;
      return;
    }
    if (!hasValue) return;

    if ((field.type === 'select' || field.type === 'radio')) {
      const allowed = new Set((field.options || []).map((option) => String(option.value || '')));
      if (!allowed.has(String(value))) {
        errors[key] = `${label} must be one of the configured options.`;
      }
    } else if (field.type === 'checkbox_group') {
      const allowed = new Set((field.options || []).map((option) => String(option.value || '')));
      const selectedValues = Array.isArray(value) ? value : [];
      if (selectedValues.some((item) => !allowed.has(String(item)))) {
        errors[key] = `${label} must only include configured options.`;
      }
    } else if (field.type === 'url' && !isValidUrl(String(value))) {
      errors[key] = `${label} must be a valid URL.`;
    } else if (field.type === 'rating') {
      const numeric = Number(value);
      const maxStars = Number(field.max_stars || 5);
      if (!Number.isInteger(numeric) || numeric < 1 || numeric > maxStars) {
        errors[key] = `${label} must be between 1 and ${maxStars}.`;
      }
    }
  });

  return errors;
};

interface FormFieldRendererProps {
  fields: FormField[];
  values: FormValues;
  errors: FormErrors;
  onChange: (key: string, value: FormFieldValue) => void;
}

const FieldError: React.FC<{ message?: string }> = ({ message }) => {
  if (!message) return null;
  return <p className="text-xs font-semibold text-red-600">{message}</p>;
};

export const FormFieldRenderer: React.FC<FormFieldRendererProps> = ({
  fields,
  values,
  errors,
  onChange,
}) => {
  return (
    <>
      {fields.map((field, index) => {
        const key = getFormFieldKey(field, index);
        const label = field.label || key;
        const type = field.type || 'text';
        const value = values[key] ?? '';
        const options = Array.isArray(field.options) ? field.options : [];
        const placeholder = field.placeholder || `Enter ${label.toLowerCase()}`;
        const liveUrlError = type === 'url' && value ? !isValidUrl(String(value)) : false;
        const hasError = Boolean(errors[key]) || liveUrlError;
        const controlClass = `${inputClass} ${hasError ? errorClass : normalClass}`;

        if (type === 'radio') {
          const stacked = field.layout !== 'inline';
          return (
            <fieldset key={`${key}_${index}`} className="space-y-2">
              <legend className="block text-xs font-black uppercase tracking-widest text-slate-500">
                {label}
                {field.required ? ' *' : ''}
              </legend>
              <div className={stacked ? 'space-y-2' : 'flex flex-wrap gap-4'}>
                {options.map((option, optionIndex) => {
                  const optionValue = String(option.value || '');
                  return (
                    <label
                      key={`${key}_${optionValue}_${optionIndex}`}
                      className={`${stacked ? 'flex w-full' : 'inline-flex'} items-center gap-2 text-sm font-semibold text-slate-700`}
                    >
                      <input
                        type="radio"
                        name={key}
                        value={optionValue}
                        checked={String(value) === optionValue}
                        required={Boolean(field.required)}
                        onChange={() => onChange(key, optionValue)}
                        className="h-4 w-4 border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      {option.label || optionValue}
                    </label>
                  );
                })}
              </div>
              <FieldError message={errors[key]} />
            </fieldset>
          );
        }

        if (type === 'checkbox') {
          return (
            <div key={`${key}_${index}`} className="space-y-2">
              <label className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700">
                <input
                  type="checkbox"
                  name={key}
                  checked={Boolean(value)}
                  onChange={(event) => onChange(key, event.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
                {label}
                {field.required ? ' *' : ''}
              </label>
              <FieldError message={errors[key]} />
            </div>
          );
        }

        if (type === 'checkbox_group') {
          const selectedValues = Array.isArray(value) ? value.map(String) : [];
          return (
            <fieldset key={`${key}_${index}`} className="space-y-2">
              <legend className="block text-xs font-black uppercase tracking-widest text-slate-500">
                {label}
                {field.required ? ' *' : ''}
              </legend>
              <div className="space-y-2">
                {options.map((option, optionIndex) => {
                  const optionValue = String(option.value || '');
                  return (
                    <label
                      key={`${key}_${optionValue}_${optionIndex}`}
                      className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700"
                    >
                      <input
                        type="checkbox"
                        name={key}
                        value={optionValue}
                        checked={selectedValues.includes(optionValue)}
                        onChange={(event) => {
                          const next = event.target.checked
                            ? [...selectedValues, optionValue]
                            : selectedValues.filter((item) => item !== optionValue);
                          onChange(key, next);
                        }}
                        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      {option.label || optionValue}
                    </label>
                  );
                })}
              </div>
              <FieldError message={errors[key]} />
            </fieldset>
          );
        }

        if (type === 'rating') {
          const selected = Number(value) || 0;
          const maxStars = Number(field.max_stars || 5);
          return (
            <div key={`${key}_${index}`} className="space-y-2">
              <p className="block text-xs font-black uppercase tracking-widest text-slate-500">
                {label}
                {field.required ? ' *' : ''}
              </p>
              <div className="flex items-center gap-1">
                {Array.from({ length: maxStars }, (_, starIndex) => {
                  const rating = starIndex + 1;
                  return (
                    <button
                      key={rating}
                      type="button"
                      onClick={() => onChange(key, rating)}
                      className={`text-3xl leading-none transition hover:text-amber-400 ${
                        rating <= selected ? 'text-amber-400' : 'text-slate-300'
                      }`}
                      aria-label={`${rating} star${rating === 1 ? '' : 's'}`}
                    >
                      ★
                    </button>
                  );
                })}
              </div>
              <FieldError message={errors[key]} />
            </div>
          );
        }

        return (
          <div key={`${key}_${index}`} className="space-y-2">
            <label className="block text-xs font-black uppercase tracking-widest text-slate-500">
              {label}
              {field.required ? ' *' : ''}
            </label>
            {type === 'textarea' ? (
              <textarea
                name={key}
                required={Boolean(field.required)}
                value={String(value)}
                placeholder={placeholder}
                onChange={(event) => onChange(key, event.target.value)}
                className={`min-h-[120px] ${controlClass}`}
              />
            ) : type === 'select' ? (
              <select
                name={key}
                required={Boolean(field.required)}
                value={String(value)}
                onChange={(event) => onChange(key, event.target.value)}
                className={controlClass}
              >
                <option value="" disabled>
                  {field.placeholder || `Select ${label.toLowerCase()}`}
                </option>
                {options.map((option, optionIndex) => (
                  <option key={`${key}_${option.value}_${optionIndex}`} value={String(option.value || '')}>
                    {option.label || option.value}
                  </option>
                ))}
              </select>
            ) : type === 'phone' && field.default_country_code ? (
              <div className={`flex overflow-hidden rounded-2xl border bg-slate-50 transition focus-within:border-blue-500 focus-within:bg-white ${hasError ? 'border-red-400' : 'border-slate-200'}`}>
                <span className="inline-flex items-center border-r border-slate-200 px-4 text-sm font-bold text-slate-500">
                  {field.default_country_code}
                </span>
                <input
                  name={key}
                  type="text"
                  required={Boolean(field.required)}
                  value={String(value).startsWith(field.default_country_code) ? String(value).slice(field.default_country_code.length) : String(value)}
                  placeholder={placeholder}
                  onChange={(event) => {
                    const next = event.target.value.trim();
                    onChange(key, next ? `${field.default_country_code}${next}` : '');
                  }}
                  className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm text-slate-700 outline-none"
                />
              </div>
            ) : (
              <input
                name={key}
                type={type === 'datetime' ? 'datetime-local' : type}
                required={Boolean(field.required)}
                value={String(value)}
                min={type === 'date' ? field.min_date : type === 'time' ? field.min_time : type === 'datetime' ? field.min_datetime : undefined}
                max={type === 'date' ? field.max_date : type === 'time' ? field.max_time : type === 'datetime' ? field.max_datetime : undefined}
                placeholder={placeholder}
                onChange={(event) => onChange(key, event.target.value)}
                className={controlClass}
              />
            )}
            <FieldError message={errors[key] || (liveUrlError ? `${label} must be a valid URL.` : undefined)} />
          </div>
        );
      })}
    </>
  );
};
