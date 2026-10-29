import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  ConnectionLineType,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { BulbNode } from './BulbNode';
import { CircuitEdge } from './CircuitEdge';
import { CanvasNode, CanvasEdge as CanvasEdgeType, NodeModel } from '../types';

interface CircuitCanvasProps {
  nodesData: CanvasNode[];
  edgesData: CanvasEdgeType[];
  onNodeSelect: (node: NodeModel) => void;
  selectedNodeId?: string;
}

const nodeTypes = {
  bulbNode: BulbNode,
};

const edgeTypes = {
  circuitEdge: CircuitEdge,
};

export const CircuitCanvas: React.FC<CircuitCanvasProps> = ({
  nodesData,
  edgesData,
  onNodeSelect,
  selectedNodeId,
}) => {
  // 1. 自动计算初始左右树状布局坐标
  const initialNodes: Node[] = useMemo(() => {
    if (!nodesData || nodesData.length === 0) return [];

    const nodeMap: Record<string, CanvasNode> = {};
    const inDegree: Record<string, number> = {};
    nodesData.forEach((n) => {
      nodeMap[n.id] = n;
      inDegree[n.id] = 0;
    });

    const directEdges = edgesData.filter((e) => nodeMap[e.source] && nodeMap[e.target]);
    directEdges.forEach((e) => {
      inDegree[e.target] = (inDegree[e.target] || 0) + 1;
    });

    // 计算最长层级
    const levels: Record<string, number> = {};
    const getLevel = (nid: string, visited = new Set<string>()): number => {
      if (levels[nid] !== undefined) return levels[nid];
      if (visited.has(nid)) return 0;
      visited.add(nid);

      const incoming = directEdges.filter((e) => e.target === nid);
      if (incoming.length === 0) {
        levels[nid] = 0;
        return 0;
      }
      let maxL = 0;
      incoming.forEach((e) => {
        maxL = Math.max(maxL, getLevel(e.source, new Set(visited)) + 1);
      });
      levels[nid] = maxL;
      return maxL;
    };

    nodesData.forEach((n) => getLevel(n.id));

    // 按层级分组
    const levelGroups: Record<number, CanvasNode[]> = {};
    nodesData.forEach((n) => {
      const l = levels[n.id] || 0;
      if (!levelGroups[l]) levelGroups[l] = [];
      levelGroups[l].push(n);
    });

    const cardWidth = 320;
    const cardHeight = 150;
    const gapX = 160;
    const gapY = 60;

    const result: Node[] = [];
    Object.keys(levelGroups).forEach((lStr) => {
      const l = Number(lStr);
      const group = levelGroups[l];
      group.forEach((node, idx) => {
        result.push({
          id: node.id,
          type: 'bulbNode',
          position: {
            x: 80 + l * (cardWidth + gapX),
            y: 80 + idx * (cardHeight + gapY),
          },
          data: {
            ...node,
            isSelected: node.id === selectedNodeId,
          },
        });
      });
    });

    return result;
  }, [nodesData, edgesData, selectedNodeId]);

  // 2. 映射边
  const initialEdges: Edge[] = useMemo(() => {
    return edgesData.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'circuitEdge',
      data: {
        circuitState: e.circuitState,
        flowAnimation: e.flowAnimation,
        isBypass: e.isBypass,
      },
    }));
  }, [edgesData]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // 当外部传入数据更新时同步
  React.useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  React.useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  // 点击节点事件
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const target = nodesData.find((n) => n.id === node.id);
      if (target) {
        onNodeSelect(target.raw);
      }
    },
    [nodesData, onNodeSelect]
  );

  return (
    <div className="w-full h-full bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        connectionLineType={ConnectionLineType.SmoothStep}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        className="bg-slate-950"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color="#334155" />
        <Controls className="!bg-slate-900 !border !border-slate-800 !text-slate-300 !fill-slate-300" />
        <MiniMap
          nodeColor={(n) => {
            const bulb = (n.data as any)?.bulbState;
            if (bulb === 'green_on') return '#10b981';
            if (bulb === 'blue_waiting') return '#0ea5e9';
            if (bulb === 'breathing') return '#f59e0b';
            if (bulb === 'red_alert') return '#ef4444';
            return '#475569';
          }}
          className="!bg-slate-900/80 !border !border-slate-800"
          maskColor="rgba(15, 23, 42, 0.7)"
        />
      </ReactFlow>
    </div>
  );
};
