"use client";

import { WebSocketProvider } from "@/hooks/WebSocketProvider";
import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { InlineDemo } from "@/components/landing/InlineDemo";
import { KitePillars } from "@/components/landing/KitePillars";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { OnChainProof } from "@/components/landing/OnChainProof";
import { AgentShowcase } from "@/components/landing/AgentShowcase";
import { ZeroCostBand } from "@/components/landing/ZeroCostBand";
import { Footer } from "@/components/landing/Footer";

/**
 * Landing Page (/)
 *
 * Judge flow:
 *   1. Hero — insight + live counters, "this is real" in 5s
 *   2. InlineDemo — judge runs a real query without leaving the page
 *   3. KitePillars — proof layer: Passport + x402 + Verified Intent
 *   4. HowItWorks — 5-step flow
 *   5. OnChainProof — recent tx hashes + contracts
 *   6. AgentShowcase — live marketplace grid
 *   7. ZeroCostBand — $0/month operating cost chip strip
 *   8. Footer
 *
 * The whole page shares a single WebSocket via WebSocketProvider so the
 * InlineDemo's live activity strip and the Hero counters reflect the
 * same event stream without duplicate connections.
 */
export default function LandingPage() {
  return (
    <WebSocketProvider>
      <div className="min-h-screen bg-[var(--color-bg)]">
        <Navbar />
        <Hero />
        <InlineDemo />
        <KitePillars />
        <HowItWorks />
        <OnChainProof />
        <AgentShowcase />
        <ZeroCostBand />
        <Footer />
      </div>
    </WebSocketProvider>
  );
}
