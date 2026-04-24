import React from 'react';
import { WorkflowNode } from '../../types/workflow';
import ConfigForm from './ConfigForm';

interface ImageGenConfigPanelProps {
  config: Record<string, any>;
  previousNodes?: WorkflowNode[];
  onChange: (key: string, value: any) => void;
}

const ImageGenConfigPanel: React.FC<ImageGenConfigPanelProps> = ({ config, previousNodes = [], onChange }) => (
  <ConfigForm
    nodeType="image_gen"
    config={config}
    previousNodes={previousNodes}
    onChange={onChange}
  />
);

export default ImageGenConfigPanel;
