import React from 'react';
import { NodeModel } from '../types';

interface NodeDrawerProps {
  node: NodeModel | null;
  onClose: () => void;
  onHumanSignOff: (nodeId: string) => Promise<void>;
}

export const NodeDrawer: React.FC<NodeDrawerProps> = ({
  node,
  onClose,
  onHumanSignOff,
}) => {
  if (!node) return null;

  return (
    <div className="w-[420px] border-l border-slate-800 bg-slate-900/95 backdrop-blur-2xl h-full flex flex-col shadow-2xl z-30 animate-in slide-in-from-right duration-200">
      {/* 抽屉头部 */}
      <div className="p-5 border-b border-slate-800 flex items-start justify-between">
        <div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 uppercase tracking-wider">
            {node.nodeType}
          </span>
          <h2 className="font-bold text-lg text-white mt-2 leading-tight">{node.name}</h2>
          <p className="text-xs text-slate-400 mt-1">{node.description || '无详细描述'}</p>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white text-lg font-mono p-1 rounded-md hover:bg-slate-800 transition-colors"
        >
          ✕
        </button>
      </div>

      {/* 抽屉滚动内容 */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs custom-scroll">
        {/* 状态与责任人 */}
        <div className="bg-slate-950/70 p-4 rounded-xl border border-slate-800 space-y-2.5">
          <div className="flex justify-between items-center">
            <span className="text-slate-400">当前流转状态:</span>
            <span className="font-mono font-bold text-emerald-400 px-2 py-0.5 rounded bg-emerald-950/50 border border-emerald-800">
              {node.status}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">责任人:</span>
            <span className="text-slate-200 font-medium">
              {node.assignee || '未分配'} ({node.assignRole || '-'})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">工时 (实际/预估):</span>
            <span className="text-slate-200 font-mono">
              {node.actualHours}h / {node.estimateHours}h
            </span>
          </div>
          {node.tags && node.tags.length > 0 && (
            <div className="pt-2 border-t border-slate-800 flex flex-wrap gap-1.5">
              {node.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-mono"
                >
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 外部测试系统映射 */}
        {node.externalBinding && (
          <div className="bg-indigo-950/30 p-4 rounded-xl border border-indigo-900/50 space-y-2">
            <div className="font-semibold text-indigo-300 flex items-center gap-1.5 text-sm">
              <span>⚡ 外部自动化测试映射契约</span>
            </div>
            <div className="text-[11px] text-slate-300 font-mono space-y-1 bg-slate-950/50 p-2.5 rounded border border-indigo-950">
              <div>系统: <span className="text-indigo-400 font-bold">{node.externalBinding.system}</span></div>
              <div>目标套件ID: <span className="text-amber-300 font-bold">{node.externalBinding.targetId}</span></div>
              {node.externalBinding.meta?.path && (
                <div>
                  接口探活: {node.externalBinding.meta.method}{' '}
                  <span className="text-emerald-400">{node.externalBinding.meta.path}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 验收标准 (AC) */}
        <div>
          <h3 className="font-semibold text-slate-200 mb-2.5 flex items-center gap-1.5 text-sm">
            <span>📋 客观逻辑验收标准 (AC)</span>
          </h3>
          <ul className="space-y-2">
            {node.acceptanceCriteria?.map((ac, idx) => (
              <li
                key={idx}
                className="bg-slate-950/80 p-3 rounded-lg border border-slate-800/80 text-slate-300 flex items-start gap-2.5 leading-relaxed"
              >
                <span className="text-emerald-400 font-bold mt-0.5">✓</span>
                <span>{ac}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* 审查与自动化报告 */}
        <div>
          <h3 className="font-semibold text-slate-200 mb-2.5 flex items-center gap-1.5 text-sm">
            <span>💬 自动化与人工审查记录</span>
          </h3>
          <div className="space-y-2">
            {node.review?.comments && node.review.comments.length > 0 ? (
              node.review.comments.map((c, idx) => (
                <div
                  key={idx}
                  className="bg-slate-950/90 p-3 rounded-lg border border-slate-800 text-[11px] text-slate-300 font-mono leading-relaxed"
                >
                  {c}
                </div>
              ))
            ) : (
              <div className="text-slate-500 italic p-2 bg-slate-950/40 rounded">暂无审查反馈</div>
            )}
          </div>
        </div>
      </div>

      {/* 底部两段式人工终审操作 */}
      <div className="p-5 border-t border-slate-800 bg-slate-950">
        {node.status === 'logic_verified' ? (
          <div className="space-y-3">
            <div className="text-[11px] text-sky-400 font-mono flex items-center gap-1.5">
              <span>💡 客观逻辑自动化已通过，等待人类终审签字</span>
            </div>
            <button
              onClick={() => onHumanSignOff(node.nodeId)}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-xl shadow-[0_0_20px_rgba(16,185,129,0.4)] text-xs transition-all active:scale-[0.98]"
            >
              ✓ 人工终审通过 (Sign-off) 并放电
            </button>
          </div>
        ) : node.status === 'review_pass' ? (
          <div className="text-center py-2 text-xs text-emerald-400 font-mono bg-emerald-950/30 rounded-lg border border-emerald-900/50">
            ● 节点已完全验收导通，向全链路正常输送能量
          </div>
        ) : node.status === 'review_reject' ? (
          <div className="text-center py-2 text-xs text-rose-400 font-mono bg-rose-950/30 rounded-lg border border-rose-900/50">
            ✖ 存在故障短路，请研发修复并由 Agent 重新测试
          </div>
        ) : (
          <div className="text-center py-2 text-xs text-slate-500 font-mono">
            ○ 依赖链路施工中，等待激活
          </div>
        )}
      </div>
    </div>
  );
};
