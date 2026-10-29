import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { CanvasNode } from '../types';

interface BulbNodeProps {
  data: CanvasNode & { isSelected?: boolean };
}

export const BulbNode = memo(({ data }: BulbNodeProps) => {
  const { label, nodeType, bulbState, dataOverlay, raw } = data;

  // 状态与指示灯样式映射
  let bulbBg = 'bg-slate-700 text-slate-400';
  let cardBorder = 'border-slate-800 bg-slate-900/90';
  let bulbGlowClass = '';
  let statusLabel = '待开工';

  if (bulbState === 'green_on') {
    bulbBg = 'bg-emerald-500 shadow-[0_0_15px_#10b981]';
    cardBorder = 'border-emerald-500/60 bg-emerald-950/30';
    statusLabel = '已导通·通过';
  } else if (bulbState === 'blue_waiting') {
    bulbBg = 'bg-sky-500 shadow-[0_0_15px_#0ea5e9]';
    cardBorder = 'border-sky-500/60 bg-sky-950/30';
    statusLabel = '待终审 (逻辑已过)';
  } else if (bulbState === 'breathing') {
    bulbBg = 'bg-amber-500';
    cardBorder = 'border-amber-500/60 bg-amber-950/30';
    bulbGlowClass = 'animate-breathing';
    statusLabel = '通电施工中';
  } else if (bulbState === 'red_alert') {
    bulbBg = 'bg-rose-600';
    cardBorder = 'border-rose-600/80 bg-rose-950/40';
    bulbGlowClass = 'animate-alert';
    statusLabel = '短路熔断报警';
  }

  return (
    <div
      className={`relative w-[280px] rounded-xl border-2 p-3 backdrop-blur-md shadow-2xl transition-all duration-200 ${cardBorder} hover:scale-[1.02]`}
    >
      {/* React Flow 左侧输入连接桩 */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-slate-600 !border-2 !border-slate-400 hover:!bg-emerald-400"
      />

      {/* 顶部标题与灯泡 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className={`w-3.5 h-3.5 rounded-full shrink-0 ${bulbBg} ${bulbGlowClass}`} />
          <span className="font-semibold text-sm truncate text-slate-100 hover:text-emerald-300">
            {label}
          </span>
        </div>
        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 shrink-0">
          {nodeType}
        </span>
      </div>

      {/* 状态语义说明与工时 */}
      <div className="text-xs font-mono text-slate-400 flex items-center justify-between mt-2">
        <span>{statusLabel}</span>
        <span className="text-slate-500">{dataOverlay?.hours}</span>
      </div>

      {/* 底部数据叠加 (Data Overlay) */}
      <div className="flex items-center justify-between text-[11px] pt-2 mt-2 border-t border-slate-800/80">
        <div className="flex items-center gap-1.5 text-slate-400">
          <span className="w-5 h-5 rounded-full bg-slate-800 flex items-center justify-center text-[10px] text-slate-300 font-bold">
            {dataOverlay?.assignee ? dataOverlay.assignee[0] : '?'}
          </span>
          <span className="truncate max-w-[90px]">{dataOverlay?.assignee || '未分配'}</span>
        </div>

        <div className="flex items-center gap-1.5">
          {dataOverlay?.hasExternalBinding && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-950/90 text-indigo-300 border border-indigo-700/60 font-mono">
              ⚡ 契约映射
            </span>
          )}
          {dataOverlay?.isLogicVerified && (
            <span className="text-sky-400 font-bold text-xs" title="客观断言已通过">
              ✓
            </span>
          )}
        </div>
      </div>

      {/* React Flow 右侧输出连接桩 */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-slate-600 !border-2 !border-slate-400 hover:!bg-emerald-400"
      />
    </div>
  );
});

BulbNode.displayName = 'BulbNode';
