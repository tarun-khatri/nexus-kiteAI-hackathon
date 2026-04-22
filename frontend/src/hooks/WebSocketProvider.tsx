"use client";

/**
 * WebSocketProvider — one WebSocket per page, shared across every
 * component via React context. Solves the previous bug where each
 * `useWebSocket()` call opened its OWN socket (N components = N sockets,
 * each with independent events state, making event-driven updates in
 * nested components unreliable).
 *
 * Usage:
 *   <WebSocketProvider>
 *     ...your app
 *   </WebSocketProvider>
 *
 *   const { events, connected } = useWebSocketContext();
 */

import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";

export interface NexusEvent {
  event: string;
  agent: string | null;
  target: string | null;
  data: Record<string, any>;
  message: string;
  timestamp: string;
}

interface WSContextValue {
  events: NexusEvent[];
  connected: boolean;
}

const WebSocketContext = createContext<WSContextValue>({
  events: [],
  connected: false,
});

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [events, setEvents] = useState<NexusEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>(undefined);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        // eslint-disable-next-line no-console
        console.log("[WS] Connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === "history") {
            // Prepend historical events (server sends on connect)
            setEvents((prev) => [...data.data, ...prev].slice(0, 500));
            return;
          }
          setEvents((prev) => [data, ...prev].slice(0, 500));
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error("[WS] Parse error:", e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch (e) {
      // eslint-disable-next-line no-console
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

  return (
    <WebSocketContext.Provider value={{ events, connected }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketContext(): WSContextValue {
  return useContext(WebSocketContext);
}
