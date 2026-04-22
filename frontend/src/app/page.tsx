"use client";

import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { FeatureCards } from "@/components/landing/FeatureCards";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { AgentShowcase } from "@/components/landing/AgentShowcase";
import { KitePillars } from "@/components/landing/KitePillars";
import { ContractsTable } from "@/components/landing/ContractsTable";
import { Footer } from "@/components/landing/Footer";

/**
 * Landing Page (/)
 *
 * Marketing page explaining NEXUS to hackathon judges.
 * All sections are live: Agent Showcase fetches from /api/agents,
 * Hero stats fetch from /api/stats. The dashboard lives at /dashboard.
 *
 * Sections:
 * 1. Navbar (sticky)
 * 2. Hero (headline + live stats + CTAs)
 * 3. Feature Cards (3 pillars of NEXUS)
 * 4. How It Works (5-step visual stepper)
 * 5. Agent Showcase (live grid from API)
 * 6. Kite Pillars (identity, payments, governance)
 * 7. Contracts Table (4 deployed contracts with explorer links)
 * 8. Footer
 */
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <Navbar />
      <Hero />
      <FeatureCards />
      <HowItWorks />
      <AgentShowcase />
      <KitePillars />
      <ContractsTable />
      <Footer />
    </div>
  );
}
