"use client";

import { useEffect, useState } from "react";
import { supabase, PCStatus, SyncStats, SyncEvent } from "@/lib/supabase";
import { StatCard } from "@/components/StatCard";
import { PCStatusCard } from "@/components/PCStatusCard";
import { useSyncEvents } from "@/hooks/useSyncEvents";

export default function Dashboard() {
  const [stats, setStats] = useState<SyncStats | null>(null);
  const [pcList, setPcList] = useState<PCStatus[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const { events, isConnected } = useSyncEvents(20);

  useEffect(() => {
    async function loadData() {
      try {
        // 통계 로드
        const { data: statsData } = await supabase
          .from("sync_stats")
          .select("*")
          .single();
        if (statsData) setStats(statsData);

        // PC 상태 로드
        const { data: pcData } = await supabase.from("pc_status").select("*");
        if (pcData) setPcList(pcData);

        // 오류 건수 계산
        const { count } = await supabase
          .from("sync_events")
          .select("*", { count: "exact", head: true })
          .eq("event_type", "error")
          .gte(
            "created_at",
            new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
          );
        setPendingCount(count || 0);
      } catch (e) {
        console.error("데이터 로드 실패:", e);
      } finally {
        setLoading(false);
      }
    }

    loadData();

    // 30초마다 새로고침
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  function getEventTypeLabel(type: SyncEvent["event_type"]): string {
    const labels = {
      sync: "동기화",
      error: "오류",
      batch: "배치",
      offline: "오프라인",
      recovery: "복구",
    };
    return labels[type] || type;
  }

  function getEventTypeStyle(type: SyncEvent["event_type"]): string {
    const styles = {
      sync: "bg-green-100 text-green-800",
      error: "bg-red-100 text-red-800",
      batch: "bg-blue-100 text-blue-800",
      offline: "bg-yellow-100 text-yellow-800",
      recovery: "bg-purple-100 text-purple-800",
    };
    return styles[type] || "bg-gray-100 text-gray-800";
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 연결 상태 */}
      <div className="flex items-center gap-2 text-sm">
        <span
          className={`w-2 h-2 rounded-full ${
            isConnected ? "bg-green-500" : "bg-red-500"
          }`}
        />
        <span className="text-gray-600">
          {isConnected ? "실시간 연결됨" : "연결 끊김"}
        </span>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="총 동기화"
          value={stats?.total_synced || 0}
          icon="📊"
        />
        <StatCard
          title="최근 1시간"
          value={stats?.synced_last_hour || 0}
          variant="success"
          icon="⏱️"
        />
        <StatCard
          title="활성 PC"
          value={stats?.active_pc_count || 0}
          icon="💻"
        />
        <StatCard
          title="24시간 내 오류"
          value={pendingCount}
          variant={pendingCount > 0 ? "error" : "default"}
          icon="⚠️"
        />
      </div>

      {/* PC 상태 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">PC 상태</h2>
        {pcList.length === 0 ? (
          <p className="text-gray-500">등록된 PC가 없습니다</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {pcList.map((pc) => (
              <PCStatusCard key={pc.gfx_pc_id} pc={pc} />
            ))}
          </div>
        )}
      </div>

      {/* 최근 이벤트 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">최근 이벤트</h2>
        {events.length === 0 ? (
          <p className="text-gray-500">이벤트가 없습니다</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    시간
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    PC
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    타입
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    건수
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    메시지
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {events.map((event) => (
                  <tr key={event.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(event.created_at).toLocaleTimeString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">
                      {event.gfx_pc_id}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getEventTypeStyle(
                          event.event_type
                        )}`}
                      >
                        {getEventTypeLabel(event.event_type)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {event.file_count}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate">
                      {event.error_message || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
