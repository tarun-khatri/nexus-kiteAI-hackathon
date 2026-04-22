/**
 * NEXUS - WebSocket Hook
 * Connects to the backend WebSocket for real-time dashboard updates.
 */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export interface NexusEvent {
  event: string;
  agent: string | null;
  target: string | null;
  data: Record<string, any>;
  message: string;
  timestamp: string;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export function useWebSocket() {
  const [events, setEvents] = useState<NexusEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>(undefined);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        console.log("[WS] Connected to Nexus backend");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle history (batch of past events)
          if (data.event === "history") {
            setEvents((prev) => [...data.data, ...prev].slice(0, 200));
            return;
          }

          // Handle single event
          setEvents((prev) => [data, ...prev].slice(0, 200));
        } catch (e) {
          console.error("[WS] Parse error:", e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        console.log("[WS] Disconnected, reconnecting in 3s...");
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch (e) {
      console.error("[WS] Connection error:", e);
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, connected };
}
