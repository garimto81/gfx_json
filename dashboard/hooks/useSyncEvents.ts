"use client";

import { useEffect, useState } from "react";
import { supabase, SyncEvent } from "@/lib/supabase";
import { RealtimeChannel } from "@supabase/supabase-js";

export function useSyncEvents(limit: number = 50) {
  const [events, setEvents] = useState<SyncEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 초기 데이터 로드
    async function loadEvents() {
      try {
        const { data, error: fetchError } = await supabase
          .from("sync_events")
          .select("*")
          .order("created_at", { ascending: false })
          .limit(limit);

        if (fetchError) throw fetchError;
        setEvents(data || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "데이터 로드 실패");
      }
    }

    loadEvents();

    // Realtime 구독
    const channel: RealtimeChannel = supabase
      .channel("sync-events-realtime")
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "sync_events",
        },
        (payload) => {
          const newEvent = payload.new as SyncEvent;
          setEvents((prev) => [newEvent, ...prev].slice(0, limit));
        }
      )
      .subscribe((status) => {
        setIsConnected(status === "SUBSCRIBED");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [limit]);

  return { events, isConnected, error };
}
