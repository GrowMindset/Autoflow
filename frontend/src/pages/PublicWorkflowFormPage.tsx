import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { PublicFormDefinition, workflowService } from '../services/workflowService';

const PublicWorkflowFormPage: React.FC = () => {
  const { pathToken } = useParams<{ pathToken: string }>();
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formDefinition, setFormDefinition] = useState<PublicFormDefinition | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});

  useEffect(() => {
    const loadForm = async () => {
      if (!pathToken) return;
      setIsLoading(true);
      try {
        const payload = await workflowService.getPublicFormDefinition(pathToken);
        setFormDefinition(payload);

        const initialValues: Record<string, string> = {};
        payload.fields.forEach((field, index) => {
          const key = field.name || `field_${index + 1}`;
          initialValues[key] = '';
        });
        setFormValues(initialValues);
      } catch (error: any) {
        const message =
          error?.response?.data?.detail ||
          error?.message ||
          'Could not load public form.';
        toast.error(String(message));
      } finally {
        setIsLoading(false);
      }
    };

    void loadForm();
  }, [pathToken]);

  const fields = useMemo(() => formDefinition?.fields || [], [formDefinition]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!pathToken || !formDefinition) return;

    setIsSubmitting(true);
    try {
      await workflowService.submitPublicForm(pathToken, formValues);
      toast.success('Form submitted successfully.');
      setFormValues((prev) =>
        Object.keys(prev).reduce<Record<string, string>>((acc, key) => {
          acc[key] = '';
          return acc;
        }, {})
      );
    } catch (error: any) {
      const message =
        error?.response?.data?.detail ||
        error?.message ||
        'Form submission failed.';
      toast.error(String(message));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
        <div className="rounded-2xl bg-white border border-slate-200 px-6 py-5 text-sm font-semibold text-slate-600 shadow-sm">
          Loading form...
        </div>
      </div>
    );
  }

  if (!formDefinition) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
        <div className="w-full max-w-xl rounded-3xl bg-white border border-slate-200 p-8 shadow-sm space-y-4">
          <h1 className="text-xl font-black text-slate-900">Form Not Available</h1>
          <p className="text-sm text-slate-600">
            This published form could not be loaded. It may be unpublished or invalid.
          </p>
          <Link
            to="/"
            className="inline-flex items-center rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold uppercase tracking-wider text-white"
          >
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 py-10 px-4">
      <div className="mx-auto w-full max-w-2xl space-y-5">
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
          <p className="text-[11px] uppercase tracking-widest font-black text-slate-400">Published Form</p>
          <h1 className="mt-1 text-2xl font-black text-slate-900">
            {formDefinition.form_title || formDefinition.workflow_name}
          </h1>
          {formDefinition.form_description ? (
            <p className="mt-2 text-sm text-slate-600">{formDefinition.form_description}</p>
          ) : null}
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-3xl border border-slate-200 bg-white px-6 py-6 shadow-sm space-y-4"
        >
          {fields.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm text-slate-500">
              No fields configured in this form.
            </div>
          ) : (
            fields.map((field, index) => {
              const fieldName = field.name || `field_${index + 1}`;
              const label = field.label || fieldName;
              const inputType = field.type === 'textarea' ? 'textarea' : (field.type || 'text');
              const value = formValues[fieldName] ?? '';

              return (
                <div key={`${fieldName}_${index}`} className="space-y-2">
                  <label className="block text-xs font-black uppercase tracking-widest text-slate-500">
                    {label}
                    {field.required ? ' *' : ''}
                  </label>
                  {inputType === 'textarea' ? (
                    <textarea
                      required={Boolean(field.required)}
                      value={value}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, [fieldName]: e.target.value }))}
                      className="min-h-[120px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white"
                    />
                  ) : (
                    <input
                      type={inputType}
                      required={Boolean(field.required)}
                      value={value}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, [fieldName]: e.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white"
                    />
                  )}
                </div>
              );
            })
          )}

          <button
            type="submit"
            disabled={isSubmitting || fields.length === 0}
            className="inline-flex items-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800 disabled:opacity-50"
          >
            {isSubmitting ? 'Submitting...' : 'Submit Form'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default PublicWorkflowFormPage;
