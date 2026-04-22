"use client";

import { X } from "lucide-react";

interface SlidePanelProps {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  badge?: string | number;
}

export function SlidePanel({ title, isOpen, onClose, children, badge }: SlidePanelProps) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed bottom-14 left-0 right-0 z-50 animate-fade-in">
        <div className="container-main">
          <div className="card shadow-lg max-h-[50vh] flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)] shrink-0">
              <div className="flex items-center gap-2">
                <h3 className="font-heading text-sm font-semibold">{title}</h3>
                {badge !== undefined && (
                  <span className="badge badge-orange text-[10px]">{badge}</span>
                )}
              </div>
              <button
                onClick={onClose}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors p-1"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="overflow-y-auto p-5 flex-1">
              {children}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
