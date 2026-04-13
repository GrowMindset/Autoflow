import axios from 'axios';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface WorkflowDefinition {
  nodes: any[];
  edges: any[];
}

export interface AIResponse {
  message: string;
  workflow?: WorkflowDefinition;
}

class AIService {
  private messages: Message[] = [];

  async generateWorkflow(prompt: string, currentWorkflow?: WorkflowDefinition): Promise<AIResponse> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1500));

    // Mock logic based on prompt keywords and context
    const lowerPrompt = prompt.toLowerCase();
    const hasExistingNodes = currentWorkflow && currentWorkflow.nodes.length > 0;
    
    // Improvement/Context Awareness Mock
    if (hasExistingNodes && (lowerPrompt.includes('add') || lowerPrompt.includes('then') || lowerPrompt.includes('improve'))) {
      const lastNode = currentWorkflow.nodes[currentWorkflow.nodes.length - 1];
      const newNodeId = `node_${Date.now()}`;
      
      return {
        message: `I've added a new action node connected to your last node (${lastNode.label}).`,
        workflow: {
          nodes: [
            ...currentWorkflow.nodes,
            {
              id: newNodeId,
              type: 'slack_action',
              label: 'Notify Team',
              position: { x: 0, y: 0 },
              config: { message: "Workflow progressed!" }
            }
          ],
          edges: [
            ...currentWorkflow.edges,
            {
              id: `edge_${Date.now()}`,
              source: lastNode.id,
              target: newNodeId
            }
          ]
        }
      };
    }

    if (lowerPrompt.includes('email') || lowerPrompt.includes('form')) {
      return {
        message: "I've designed a workflow that triggers when a form is submitted and sends an automated email response.",
        workflow: {
          nodes: [
            {
              id: 'node_1',
              type: 'form_trigger',
              label: 'Form Submission',
              position: { x: 0, y: 0 },
              config: { formId: 'contact_form' }
            },
            {
              id: 'node_2',
              type: 'email_action',
              label: 'Send Auto-reply',
              position: { x: 0, y: 0 },
              config: { 
                to: '{{submission.email}}',
                subject: 'Thank you for your submission!',
                body: 'Hi {{submission.name}}, we received your message.'
              }
            }
          ],
          edges: [
            {
              id: 'edge_1',
              source: 'node_1',
              target: 'node_2',
              sourceHandle: 'output',
              targetHandle: 'input'
            }
          ]
        }
      };
    }

    if (lowerPrompt.includes('approval') || lowerPrompt.includes('slack')) {
      return {
        message: "Here is an approval workflow. It sends a notification to Slack and waits for an manual approval before proceeding.",
        workflow: {
          nodes: [
            {
              id: 'n1',
              type: 'manual_trigger',
              label: 'Start Approval',
              position: { x: 0, y: 0 },
              config: {}
            },
            {
              id: 'n2',
              type: 'slack_action',
              label: 'Notify Slack',
              position: { x: 0, y: 0 },
              config: { channel: '#approvals', message: 'New approval request' }
            },
            {
              id: 'n3',
              type: 'if_else_transform',
              label: 'Approved?',
              position: { x: 0, y: 0 },
              config: { condition: 'approved === true' }
            }
          ],
          edges: [
            { id: 'e1', source: 'n1', target: 'n2' },
            { id: 'e2', source: 'n2', target: 'n3' }
          ]
        }
      };
    }

    return {
      message: "I'm not exactly sure how to build that yet, but I can help you with form triggers, email actions, and approval flows. Try asking for a 'Form to Email' flow!",
    };
  }
}

export const aiService = new AIService();
