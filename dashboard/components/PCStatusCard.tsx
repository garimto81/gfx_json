"use client";

import { PCStatus } from "@/lib/supabase";

interface PCStatusCardProps {
  pc: PCStatus;
}

export function PCStatusCard({ pc }: PCStatusCardProps) {
  const statusConfig = {
    online: {
      bg: "bg-green-50",
      border: "border-green-500",
      text: "text-green-800",
      icon: "●",
      label: "온라인",
    },
    idle: {
      bg: "bg-yellow-50",
      border: "border-yellow-500",
      text: "text-yellow-800",
      icon: "◐",
      label: "유휴",
    },
    offline: {
      bg: "bg-gray-100",
      border: "border-gray-400",
      text: "text-gray-600",
      icon: "○",
      label: "오프라인",
    },
  };

  const config = statusConfig[pc.status];

  function formatTime(isoString: string | null): string {
    if (!isoString) return "-";
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return "방금 전";
    if (diffMin < 60) return `${diffMin}분 전`;

    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}시간 전`;

    return date.toLocaleDateString("ko-KR");
  }

  return (
    <div
      className={`${config.bg} ${config.text} border-l-4 ${config.border} p-4 rounded-lg`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-lg">{pc.gfx_pc_id}</span>
        <span className="flex items-center gap-1">
          <span>{config.icon}</span>
          <span className="text-sm">{config.label}</span>
        </span>
      </div>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span>최근 동기화:</span>
          <span className="font-medium">{formatTime(pc.last_sync_at)}</span>
        </div>
        <div className="flex justify-between">
          <span>1시간 내:</span>
          <span className="font-medium">{pc.sessions_last_hour}건</span>
        </div>
        <div className="flex justify-between">
          <span>총 세션:</span>
          <span className="font-medium">
            {pc.total_sessions.toLocaleString()}건
          </span>
        </div>
      </div>
    </div>
  );
}
