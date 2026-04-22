/**
 * NEXUS - API Client
 * Handles all communication with the Python backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  price_per_query: number;
  status: string;
  reputation_score: number;
  total_jobs_completed: number;
  total_earned: number;
  total_spent: number;
  // From unified catalog (optional for backward compat)
  passport_id?: string | null;
  keywords?: string[];
  example_queries?: string[];
  wallet_address?: string | null;
  active?: boolean;
  source_type?: "in_process" | "http_callback" | "on_chain_only";
  callback_url?: string | null;
  registered_at?: number | null;
}

export interface SourceInfo {
  ok?: boolean;
  tried?: boolean;
  count?: number;
  error?: string | null;
  [k: string]: any;
}

export interface CategoryStatus {
  source_used: string | null;
  [subSource: string]: SourceInfo | string | null;
}

// The new envelope shape returned per-capability inside report.sections.
// Every invocation — success, failure, timeout, unreachable — uses this shape.
export interface InvocationEnvelope {
  agent_id: string;
  agent_name: string;
  capability: string;
  status: "success" | "partial" | "failed" | "timeout" | "unreachable" | "invalid_input";
  output: Record<string, any> | null;
  error_code?: string | null;
  error_message?: string | null;
  error_hint?: string | null;
  duration_ms: number;
  payment_tx_hash?: string | null;
  source: string;
  completed_at: string;
  // Orchestrator-attached:
  provider_agent_id?: string;
  provider_source?: string;
  provider_price_usdc?: number;
}

export interface Report {
  report_id: string;
  query: string;
  status?: string;            // "ok" | "partial" | "error"
  error_code?: string;        // router_unavailable | not_in_scope | no_agent_available | ...
  message?: string;
  summary: string;
  classification?: {
    status: string;
    requested_capabilities: string[];
    missing_capabilities: string[];
    reasoning?: string;
  };
  sections: Record<string, InvocationEnvelope>;   // keyed by capability name
  // Union of output fields produced by any successful envelope. The UI renders
  // whatever is here — no hardcoded verdict/confidence/score defaults.
  output_fields?: Record<string, any>;
  economy_stats: {
    total_cost_usdc: number;
    total_time_ms: number;
    agents_involved: number;
    agents_failed?: number;
    transactions: Array<{
      from: string;
      to: string;
      amount: number;
      purpose: string;
      source?: string;
      status?: string;
      tx_hash?: string | null;
    }>;
  };
  verified_intent?: Record<string, any>;
  audit_trail?: Record<string, any>;
  execution_plan?: Record<string, any>;
  // Back-compat flags (still optional, may or may not appear):
  data_sources_status?: Record<string, CategoryStatus>;
  degraded_sources?: string[];
  missing_capabilities?: string[];
  partial?: boolean;
  token?: string;
  verdict?: string;
  confidence?: string;
  score?: number;
  timestamp: string;
}

// A single capability entry from /api/capabilities
export interface CapabilityEntry {
  name: string;
  description: string;
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  enrichment_suggestions: string[];
  example_queries: string[];
  keywords: string[];
  providers: Array<{
    agent_id: string;
    agent_name: string;
    source: string;
    reputation: number;
    price_usdc: number;
  }>;
}

export interface EconomyStats {
  economy: {
    total_agents: number;
    total_transactions: number;
    total_volume_usdc: number;
    total_jobs_completed: number;
    avg_reputation: number;
  };
  agents: Record<string, {
    earned: number;
    spent: number;
    jobs: number;
    reputation: number;
    status: string;
  }>;
  governance: Record<string, number>;
}

export async function submitQuery(
  query: string,
  opts?: { enrichments?: "auto" | "off" | string[] },
): Promise<Report> {
  const body: Record<string, unknown> = { query };
  if (opts?.enrichments !== undefined) body.enrichments = opts.enrichments;
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function getCapabilities(): Promise<{
  capabilities: CapabilityEntry[];
  total_capabilities: number;
  total_providers: number;
}> {
  const res = await fetch(`${API_BASE}/api/capabilities`);
  return res.json();
}

export async function getExampleQueries(
  limit = 12,
): Promise<{
  examples: Array<{ query: string; capability: string; reputation: number }>;
  total: number;
}> {
  const res = await fetch(`${API_BASE}/api/example_queries?limit=${limit}`);
  return res.json();
}

export async function getAuditTrail(trailId: string): Promise<{
  trail_id?: string;
  traceability_hash?: string;
  report_hash?: string;
  on_chain_tx_hash?: string | null;
  explorer_url?: string | null;
  error?: string;
}> {
  const res = await fetch(`${API_BASE}/api/audit-trail/${trailId}`);
  return res.json();
}

export interface OnchainPayment {
  index: number;
  from_passport: string;
  from_agent: string | null;
  to_passport: string;
  to_agent: string | null;
  amount_usdc: number;
  purpose: string;
  mandate_id: string | null;
  timestamp_iso: string | null;
  timestamp_unix: number;
}

export async function getOnchainHistory(
  limit = 50,
): Promise<{
  payments: OnchainPayment[];
  total: number;
  source: string;
  chain_id: number;
  explorer_base: string;
  error?: string;
}> {
  const res = await fetch(`${API_BASE}/api/onchain-history?limit=${limit}`);
  return res.json();
}

export async function getAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch(`${API_BASE}/api/agents`);
  return res.json();
}

export async function getStats(): Promise<EconomyStats> {
  const res = await fetch(`${API_BASE}/api/stats`);
  return res.json();
}

export async function getTransactions(): Promise<{ transactions: any[] }> {
  const res = await fetch(`${API_BASE}/api/transactions`);
  return res.json();
}

export async function getReputation(): Promise<{ leaderboard: any[] }> {
  const res = await fetch(`${API_BASE}/api/reputation`);
  return res.json();
}

export async function updateGovernance(rules: Record<string, number>): Promise<any> {
  const res = await fetch(`${API_BASE}/api/governance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rules),
  });
  return res.json();
}

export async function getRecentEvents(): Promise<{ events: any[] }> {
  const res = await fetch(`${API_BASE}/api/events`);
  return res.json();
}

// === Marketplace ===
export interface MarketplaceAgent {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  price_per_query: number;
  reputation_score: number;
  total_jobs: number;
  active: boolean;
  registered_at: string;
  last_invoked: string | null;
  callback_url: string;
  owner_address: string;
}

export interface MarketplaceStats {
  total_agents: number;
  active_agents: number;
  total_invocations: number;
  successful_invocations: number;
  capabilities: string[];
}

export async function getMarketplaceAgents(): Promise<{ agents: MarketplaceAgent[]; stats: MarketplaceStats }> {
  const res = await fetch(`${API_BASE}/api/marketplace/agents`);
  return res.json();
}

export interface CapabilitySpecInput {
  name: string;
  description?: string;
  input_schema?: Record<string, any>;
  output_schema?: Record<string, any>;
  enrichment_suggestions?: string[];
  example_queries?: string[];
  keywords?: string[];
  price_usdc?: number;
  timeout_ms?: number;
}

export interface RegisterAgentRequest {
  name: string;
  description: string;
  capabilities: string[];
  price_per_query: number;
  callback_url: string;
  owner_address?: string;
  keywords?: string[];
  example_queries?: string[];
  // Optional rich per-capability declarations.
  capability_specs?: CapabilitySpecInput[];
}

export async function registerMarketplaceAgent(req: RegisterAgentRequest): Promise<MarketplaceAgent> {
  const res = await fetch(`${API_BASE}/api/marketplace/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Registration failed: ${res.status} ${text}`);
  }
  return res.json();
}

// === Discovery Plan ===
export interface DiscoveryPlan {
  query_type: string;
  token: string;
  confidence: number;
  capabilities_needed: string[];
  agents_selected: Array<{
    capability: string;
    agent: string;
    price: number;
    reputation: number;
    source: string;
  }>;
  estimated_cost: number;
  missing_capabilities?: string[];
  marketplace_hint?: string;
  complete?: boolean;
}

// === Reputation History ===
export interface ReputationHistoryEntry {
  timestamp: string;
  old_score: number;
  new_score: number;
  change: number;
  reason: string;
  direction: string;
}

export async function getAgentReputation(agentId: string): Promise<{
  agent: string;
  current_score: number;
  history: ReputationHistoryEntry[];
  scoring_rules: Record<string, string>;
}> {
  const res = await fetch(`${API_BASE}/api/reputation/${agentId}`);
  return res.json();
}
