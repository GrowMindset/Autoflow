import { XYPosition } from 'reactflow';
import { NODE_LIBRARY, NodeDefinition } from '../constants/nodeLibrary';
import { DEFAULT_NODE_SETTINGS } from '../constants/nodeSettings';
import { WorkflowNode } from '../types/workflow';

/**
 * Finds a node definition by its type key across all categories.
 */
export const getNodeDefinition = (type: string): NodeDefinition | undefined => {
  // Flatten all categories into a single array for easier searching
  const allNodes = Object.values(NODE_LIBRARY).flat();
  
  return allNodes.find(node => node.type === type);
};

/**
 * Creates a brand new workflow node object with a unique ID and cloned configuration.
 * Ensures the resulting node is compatible with both React Flow and the backend JSON structure.
 */
export const createNode = (type: string, position: XYPosition): WorkflowNode => {
  const definition = getNodeDefinition(type);

  if (!definition) {
    throw new Error(`[NodeFactory] Unknown node type: "${type}"`);
  }

  // Generate a unique ID (compatible with n8n style nodes e.g., 'filter_171255...')
  const id = `${type}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;

  return {
    id,
    type: definition.category, // React Flow uses category to map to BaseNode component
    position,
    data: {
      label: definition.label,
      type: definition.type,
      category: definition.category,
      // Shallow copy the default config to prevent shared state between nodes
      config: { ...DEFAULT_NODE_SETTINGS, ...definition.default_config },
      is_dummy: definition.is_dummy,
    },
  };
};
