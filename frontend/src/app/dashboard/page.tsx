"use client";

import { useState, useEffect } from "react";
import { WebSocketProvider, useWebSocketContext } from "@/hooks/WebSocketProvider";
import {
  submitQuery, getStats, getAgents, getExampleQueries,
  type EconomyStats, type AgentInfo, type Report,
} from "@/lib/api";
import { ReportDisplay } from "@/components/ReportDisplay";
import { TransactionFeed } from "@/components/TransactionFeed";
import { OnchainHistoryPanel } from "@/components/OnchainHistoryPanel";
import { GovernancePanel } from "@/components/GovernancePanel";
import { MarketplaceBrowser } from "@/components/MarketplaceBrowser";
import CircuitBreakerAlert from "@/components/CircuitBreakerAlert";
import { NexusLogo } from "@/components/ui/NexusLogo";
import { BottomBar, type PanelTab } from "@/components/dashboard/BottomBar";
import { SlidePanel } from "@/components/dashboard/SlidePanel";
import { HashLink } from "@/components/ui/HashLink";
import Link from "next/link";
import { Search, Loader2, ArrowLeft } from "lucide-react";

type ActivityTab = "live" | "history";

function DashboardInner() {
  const { events, connected } = useWebSocketContext();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [stats, setStats] = useState<EconomyStats | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [circuitBreakerBlocks, setCircuitBreakerBlocks] = useState<any[]>([]);
  const [activePanel, setActivePanel] = useState<PanelTab>(null);
  const [activityTab, setActivityTab] = useState<ActivityTab>("live");
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    const fetchData = async () => {
      const [s, a] = await Promise.all([
        getStats().catch(() => null),
        getAgents().catch(() => ({ agents: [] as AgentInfo[] })),
      ]);
      if (s) setStats(s);
      if (a && a.agents) setAgents(a.agents);
    };
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const fetchSuggestions = async () => {
      const res = await getExampleQueries(8).catch(() => null);
      if (!cancelled && res) {
        setSuggestions(res.examples.map((e) => e.query));
      }
    };
    fetchSuggestions();
    const id = setInterval(fetchSuggestions, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    if (latest.event === "circuit_breaker_blocked" && latest.data) {
      setCircuitBreakerBlocks((prev) => [latest.data, ...prev]);
      setTimeout(() => setCircuitBreakerBlocks((prev) => prev.slice(0, -1)), 10000);
    }
  }, [events]);

  const handleSubmit = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setReport(null);
    setActivePanel(null);
    try {
      const result = await submitQuery(query);
      setReport(result);
    } catch (e) {
      console.error("Query failed:", e);
    }
    const [s, a] = await Promise.all([
      getStats().catch(() => null),
      getAgents().catch(() => null),
    ]);
    if (s) setStats(s);
    if (a && a.agents) setAgents(a.agents);
    setLoading(false);
  };

  const refreshData = async () => {
    const [s, a] = await Promise.all([
      getStats().catch(() => null),
      getAgents().catch(() => null),
    ]);
    if (s) setStats(s);
    if (a && a.agents) setAgents(a.agents);
  };

  const sortedAgents = [...agents].sort((a, b) => b.reputation_score - a.reputation_score);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-16">
      <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-[var(--color-border)]">
        <div className="max-w-3xl mx-auto px-4 flex items-center justify-between h-12">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors no-underline">
              <ArrowLeft size={16} />
            </Link>
            <NexusLogo size="sm" showText={false} />
            <span className="font-heading font-bold text-sm">NEXUS</span>
          </div>
          {stats && (
            <div className="hidden sm:flex items-center gap-4 text-[11px] text-[var(--color-text-muted)]">
              <span>{stats.economy.total_agents} agents</span>
              <span>${stats.economy.total_volume_usdc.toFixed(4)} vol</span>
              <span>{stats.economy.total_transactions} txns</span>
            </div>
          )}
          <div className={`flex items-center gap-1.5 text-xs font-medium ${connected ? "text-[var(--color-green)]" : "text-[var(--color-red)]"}`}>
            <div className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-[var(--color-green)] animate-pulse" : "bg-[var(--color-red)]"}`} />
            {connected ? "Live" : "Offline"}
          </div>
        </div>
      </header>

      {circuitBreakerBlocks.length > 0 && (
        <div className="max-w-3xl mx-auto px-4 pt-3 space-y-2">
          {circuitBreakerBlocks.map((block, i) => (
            <CircuitBreakerAlert key={i} block={block} />
          ))}
        </div>
      )}

      <div className="max-w-3xl mx-auto px-4 pt-8 pb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-faint)]" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="Ask anything about crypto..."
                className="input pl-9 text-sm sm:text-base py-2.5"
              />
            </div>
            <button
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              className="btn-primary px-5 py-2.5 shrink-0"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : "Go"}
            </button>
          </div>
          <div className="mt-2.5 flex gap-1.5 flex-wrap">
            {suggestions.length === 0 ? (
              <span className="text-[11px] text-[var(--color-text-faint)]">
                Suggestions load from registered agents' example queries…
              </span>
            ) : (
              suggestions.map((q) => (
                <button
                  key={q}
                  onClick={() => setQuery(q)}
                  className="text-[11px] px-2.5 py-1 rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-all cursor-pointer bg-white"
                >
                  {q}
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 pb-8">
        {report ? (
          <div className="card p-5 sm:p-8 animate-fade-in">
            <ReportDisplay report={report} />
          </div>
        ) : !loading ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-[var(--color-bg-alt)] flex items-center justify-center mx-auto mb-4">
              <Search size={24} className="text-[var(--color-text-faint)]" />
            </div>
            <h3 className="font-heading text-lg font-semibold text-[var(--color-text-secondary)] mb-1.5">
              Ask the Agent Economy
            </h3>
            <p className="text-sm text-[var(--color-text-muted)] max-w-md mx-auto">
              Submit a query above. Autonomous agents will discover each other, execute work,
              pay via x402 micropayments, and deliver a verified report.
            </p>
          </div>
        ) : (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-[var(--color-bg-alt)] flex items-center justify-center mx-auto mb-4">
              <Loader2 size={24} className="text-[var(--color-accent)] animate-spin" />
            </div>
            <h3 className="font-heading text-base font-semibold text-[var(--color-text-secondary)] mb-1">
              Agents are working...
            </h3>
            <p className="text-sm text-[var(--color-text-muted)]">
              Discovering → Paying → Executing → Auditing → Compiling
            </p>
          </div>
        )}
      </div>

      {/* Activity panel: two tabs (Live events + On-chain history) */}
      <SlidePanel
        title="Activity"
        isOpen={activePanel === "activity"}
        onClose={() => setActivePanel(null)}
        badge={events.length || undefined}
      >
        <div className="mb-3 flex gap-1 border-b border-[var(--color-border)]">
          <button
            type="button"
            onClick={() => setActivityTab("live")}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activityTab === "live"
                ? "border-[var(--color-accent)] text-[var(--color-text)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            Live ({events.length})
          </button>
          <button
            type="button"
            onClick={() => setActivityTab("history")}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              activityTab === "history"
                ? "border-[var(--color-accent)] text-[var(--color-text)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            On-chain History
          </button>
        </div>
        {activityTab === "live"
          ? <TransactionFeed events={events} />
          : <OnchainHistoryPanel />
        }
      </SlidePanel>

      {/* Agents panel — full agent names, passports as HashLinks */}
      <SlidePanel
        title="Agent Marketplace"
        isOpen={activePanel === "agents"}
        onClose={() => setActivePanel(null)}
        badge={agents.length || undefined}
      >
        <div className="space-y-2">
          {sortedAgents.map((agent) => {
            const isExt = agent.source_type === "http_callback";
            const isChain = agent.source_type === "on_chain_only";
            return (
              <div
                key={agent.agent_id}
                className="py-2.5 px-3 rounded-lg hover:bg-[var(--color-bg-alt)] transition-colors border border-[var(--color-border)] space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-sm font-medium break-words">{agent.name}</span>
                    {isExt && <span className="badge badge-blue text-[9px] shrink-0">EXT</span>}
                    {isChain && <span className="badge badge-purple text-[9px] shrink-0">CHAIN</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)] shrink-0">
                    <span className={agent.reputation_score >= 70 ? "text-[var(--color-green)]" : agent.reputation_score >= 40 ? "text-[var(--color-amber)]" : "text-[var(--color-red)]"}>
                      rep {agent.reputation_score}
                    </span>
                    <span className="font-mono">${agent.total_earned.toFixed(4)}</span>
                    <span>{agent.total_jobs_completed} jobs</span>
                  </div>
                </div>
                {agent.passport_id && (
                  <HashLink value={agent.passport_id} kind="passport" label="passport" />
                )}
              </div>
            );
          })}
          {agents.length === 0 && (
            <p className="text-sm text-[var(--color-text-muted)] text-center py-8">Loading agents...</p>
          )}
        </div>
      </SlidePanel>

      <SlidePanel
        title="Governance Controls"
        isOpen={activePanel === "governance"}
        onClose={() => setActivePanel(null)}
      >
        <div className="max-w-sm">
          <GovernancePanel currentRules={stats?.governance} />
        </div>
      </SlidePanel>

      {activePanel === "register" && (
        <div className="fixed inset-0 z-50">
          <MarketplaceBrowser onRegistered={() => { setActivePanel(null); refreshData(); }} />
        </div>
      )}

      <BottomBar
        activeTab={activePanel}
        onTabChange={setActivePanel}
        eventCount={events.length}
        agentCount={agents.length}
      />
    </div>
  );
}

export default function DashboardPage() {
  return (
    <WebSocketProvider>
      <DashboardInner />
    </WebSocketProvider>
  );
}
