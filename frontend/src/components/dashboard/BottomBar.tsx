"use client";

import { Activity, Users, Settings, Plus } from "lucide-react";

export type PanelTab = "activity" | "agents" | "governance" | "register" | null;

interface BottomBarProps {
  activeTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  eventCount?: number;
  agentCount?: number;
}

const TABS: { id: PanelTab; label: string; icon: typeof Activity }[] = [
  { id: "activity", label: "Activity", icon: Activity },
  { id: "agents", label: "Agents", icon: Users },
  { id: "governance", label: "Governance", icon: Settings },
  { id: "register", label: "Register", icon: Plus },
];

export function BottomBar({ activeTab, onTabChange, eventCount, agentCount }: BottomBarProps) {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-md border-t border-[var(--color-border)]">
      <div className="container-main flex items-center justify-center gap-1 h-14">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;
          const count = tab.id === "activity" ? eventCount : tab.id === "agents" ? agentCount : undefined;

          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(isActive ? null : tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? "bg-[var(--color-accent)] text-white shadow-sm"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-alt)] hover:text-[var(--color-text)]"
              }`}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{tab.label}</span>
              {count !== undefined && count > 0 && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                  isActive ? "bg-white/20 text-white" : "bg-[var(--color-bg-alt)] text-[var(--color-text-muted)]"
                }`}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
