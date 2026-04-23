"use client";

import { useState } from "react";
import Link from "next/link";
import { NexusLogo } from "@/components/ui/NexusLogo";
import { Menu, X } from "lucide-react";

const NAV_LINKS = [
  { label: "Live Demo", href: "#demo" },
  { label: "Pulse", href: "/pulse" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Agents", href: "#agents" },
  { label: "Contracts", href: "#contracts" },
];

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-[var(--color-border)]">
      <div className="container-main flex items-center justify-between h-16">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 no-underline">
          <NexusLogo size="sm" />
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors no-underline"
            >
              {link.label}
            </a>
          ))}
          <Link href="/dashboard" className="btn-primary text-sm no-underline">
            Launch Dashboard →
          </Link>
        </div>

        {/* Mobile menu button */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden p-2 text-[var(--color-text-secondary)]"
          aria-label="Toggle menu"
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-[var(--color-border)] bg-white px-4 py-4 space-y-3">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="block text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] no-underline py-2"
            >
              {link.label}
            </a>
          ))}
          <Link
            href="/dashboard"
            className="btn-primary w-full text-center text-sm no-underline block"
          >
            Launch Dashboard →
          </Link>
        </div>
      )}
    </nav>
  );
}
