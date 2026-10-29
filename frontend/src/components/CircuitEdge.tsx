import React from 'react';
import { BaseEdge, getBezierPath, EdgeProps } from '@xyflow/react';

export const CircuitEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) => {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const circuitState = (data?.circuitState as string) || 'dormant';
  const flowAnimation = Boolean(data?.flowAnimation);
  const isBypass = Boolean(data?.isBypass);

  const isEnergized = circuitState === 'energized';
  const isBlocked = circuitState === 'blocked';

  return (
    <>
      {/* 底层基础导线 */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke={isBlocked ? '#7f1d1d' : isEnergized ? '#064e3b' : '#334155'}
        strokeWidth={isEnergized ? 4 : 2}
        strokeDasharray={isBypass ? '4,4' : 'none'}
        className="react-flow__edge-path"
      />

      {/* 通电电流动态流动粒子 */}
      {flowAnimation && (
        <path
          d={edgePath}
          fill="none"
          stroke="#10B981"
          strokeWidth={3.5}
          className="flow-wire"
          style={{ filter: 'drop-shadow(0 0 6px #10b981)' }}
        />
      )}

      {/* 故障报警熔断虚线 */}
      {isBlocked && (
        <path
          d={edgePath}
          fill="none"
          stroke="#EF4444"
          strokeWidth={3}
          strokeDasharray="6,4"
          style={{ filter: 'drop-shadow(0 0 8px #ef4444)' }}
        />
      )}
    </>
  );
};
