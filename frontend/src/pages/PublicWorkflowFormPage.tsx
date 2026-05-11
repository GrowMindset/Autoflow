import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { PublicFormDefinition, workflowService } from '../services/workflowService';
import {
  FormErrors,
  FormFieldRenderer,
  FormValues,
  initializeFormValues,
  readFormValuesFromElement,
  validateFormValues,
} from '../components/forms/FormFieldRenderer';

const PublicWorkflowFormPage: React.FC = () => {
  const { pathToken } = useParams<{ pathToken: string }>();
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formDefinition, setFormDefinition] = useState<PublicFormDefinition | null>(null);
  const [formValues, setFormValues] = useState<FormValues>({});
  const [formErrors, setFormErrors] = useState<FormErrors>({});

  useEffect(() => {
    const loadForm = async () => {
      if (!pathToken) return;
      setIsLoading(true);
      try {
        const payload = await workflowService.getPublicFormDefinition(pathToken);
        setFormDefinition(payload);

        setFormValues(initializeFormValues(payload.fields));
        setFormErrors({});
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
    const submittedValues = readFormValuesFromElement(event.currentTarget as HTMLFormElement, fields, formValues);
    setFormValues(submittedValues);
    const validationErrors = validateFormValues(fields, submittedValues);
    setFormErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      toast.error('Please fix the highlighted fields.');
      return;
    }

    setIsSubmitting(true);
    try {
      await workflowService.submitPublicForm(pathToken, submittedValues);
      toast.success('Form submitted successfully.');
      setFormValues(initializeFormValues(fields));
      setFormErrors({});
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
            <FormFieldRenderer
              fields={fields}
              values={formValues}
              errors={formErrors}
              onChange={(key, value) => {
                setFormValues((prev) => ({ ...prev, [key]: value }));
                setFormErrors((prev) => ({ ...prev, [key]: '' }));
              }}
            />
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
