import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { workflowService } from '../services/workflowService';
import { executionService } from '../services/executionService';

type FormField = {
  name?: string;
  label?: string;
  type?: string;
  required?: boolean;
};

type WorkflowNode = {
  id: string;
  type: string;
  config?: Record<string, any>;
};

const FORM_EXECUTION_MESSAGE_TYPE = 'autoflow:form-execution-started';

const WorkflowFormPage: React.FC = () => {
  const { workflowId } = useParams<{ workflowId: string }>();
  const [searchParams] = useSearchParams();
  const requestedNodeId = searchParams.get('nodeId');

  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workflowName, setWorkflowName] = useState('Workflow Form');
  const [formNode, setFormNode] = useState<WorkflowNode | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});

  useEffect(() => {
    const loadWorkflow = async () => {
      if (!workflowId) return;
      setIsLoading(true);
      try {
        const workflow = await workflowService.getWorkflow(workflowId);
        if (!workflow?.definition) {
          toast.error('Could not load workflow form.');
          return;
        }

        setWorkflowName(workflow.name || 'Workflow Form');

        const nodes: WorkflowNode[] = Array.isArray(workflow.definition.nodes)
          ? workflow.definition.nodes
          : [];
        const edges: Array<{ source: string; target: string }> = Array.isArray(workflow.definition.edges)
          ? workflow.definition.edges
          : [];

        const formNodes = nodes.filter((node) => node.type === 'form_trigger');
        if (formNodes.length === 0) {
          setFormNode(null);
          return;
        }

        const indegree = new Map<string, number>();
        nodes.forEach((node) => indegree.set(node.id, 0));
        edges.forEach((edge) => indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1));

        const rootFormNode = formNodes.find((node) => (indegree.get(node.id) || 0) === 0) || formNodes[0];
        const explicitNode = requestedNodeId
          ? formNodes.find((node) => node.id === requestedNodeId)
          : null;
        const chosenNode = explicitNode || rootFormNode;
        setFormNode(chosenNode);

        const fields: FormField[] = Array.isArray(chosenNode.config?.fields)
          ? chosenNode.config?.fields
          : [];
        const initialValues: Record<string, string> = {};
        fields.forEach((field, idx) => {
          const key = field?.name || `field_${idx + 1}`;
          initialValues[key] = '';
        });
        setFormValues(initialValues);
      } finally {
        setIsLoading(false);
      }
    };

    void loadWorkflow();
  }, [workflowId, requestedNodeId]);

  const formFields = useMemo<FormField[]>(() => {
    if (!formNode) return [];
    return Array.isArray(formNode.config?.fields) ? formNode.config?.fields : [];
  }, [formNode]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!workflowId) return;

    setIsSubmitting(true);
    try {
      const enqueue = await executionService.runWorkflowForm(workflowId, {
        form_data: formValues,
      });
      toast.success('Form submitted successfully.');

      window.setTimeout(() => {
        try {
          if (window.opener && !window.opener.closed) {
            window.opener.postMessage(
              {
                type: FORM_EXECUTION_MESSAGE_TYPE,
                workflowId,
                executionId: enqueue.execution_id,
              },
              window.location.origin,
            );
            window.opener.focus();
            window.close();
            window.setTimeout(() => {
              if (!window.closed) {
                window.location.reload();
              }
            }, 200);
            return;
          }
        } catch (error) {
          console.warn('Could not close form tab after submit:', error);
        }

        window.location.reload();
      }, 500);
    } catch (error: any) {
      const message =
        error?.response?.data?.detail?.message ||
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

  if (!formNode) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
        <div className="w-full max-w-xl rounded-3xl bg-white border border-slate-200 p-8 shadow-sm space-y-4">
          <h1 className="text-xl font-black text-slate-900">No Form Trigger Found</h1>
          <p className="text-sm text-slate-600">
            This workflow does not have a `form_trigger` node, so there is no form page to render.
          </p>
          <Link
            to="/"
            className="inline-flex items-center rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold uppercase tracking-wider text-white"
          >
            Back to Builder
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 py-10 px-4">
      <div className="mx-auto w-full max-w-2xl space-y-5">
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
          <p className="text-[11px] uppercase tracking-widest font-black text-slate-400">Workflow Form</p>
          <h1 className="mt-1 text-2xl font-black text-slate-900">
            {formNode.config?.form_title || workflowName}
          </h1>
          {formNode.config?.form_description ? (
            <p className="mt-2 text-sm text-slate-600">{String(formNode.config.form_description)}</p>
          ) : null}
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-3xl border border-slate-200 bg-white px-6 py-6 shadow-sm space-y-4"
        >
          {formFields.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm text-slate-500">
              No fields configured in this form trigger.
            </div>
          ) : (
            formFields.map((field, index) => {
              const fieldName = field?.name || `field_${index + 1}`;
              const label = field?.label || fieldName;
              const inputType = field?.type === 'textarea' ? 'textarea' : (field?.type || 'text');
              const value = formValues[fieldName] ?? '';

              return (
                <div key={`${fieldName}_${index}`} className="space-y-2">
                  <label className="block text-xs font-black uppercase tracking-widest text-slate-500">
                    {label}
                    {field?.required ? ' *' : ''}
                  </label>
                  {inputType === 'textarea' ? (
                    <textarea
                      required={Boolean(field?.required)}
                      value={value}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, [fieldName]: e.target.value }))}
                      className="min-h-[120px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white"
                    />
                  ) : (
                    <input
                      type={inputType}
                      required={Boolean(field?.required)}
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
            disabled={isSubmitting || formFields.length === 0}
            className="inline-flex items-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800 disabled:opacity-50"
          >
            {isSubmitting ? 'Submitting...' : 'Submit Form'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default WorkflowFormPage;
