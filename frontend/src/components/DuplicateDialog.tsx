"use client";

import { RefreshCw, Zap, X } from "lucide-react";

interface DuplicateCompany {
  company_name: string;
  domain: string;
}

interface DuplicateDialogProps {
  duplicates: DuplicateCompany[];
  onScratch: () => void;
  onIncremental: () => void;
  onCancel: () => void;
}

export default function DuplicateDialog({
  duplicates,
  onScratch,
  onIncremental,
  onCancel,
}: DuplicateDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
        onClick={onCancel}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-md mx-4 rounded-2xl p-6 shadow-2xl animate-fade-in"
        style={{
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border-faint)",
        }}
      >
        {/* Close */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-lg opacity-60 hover:opacity-100 transition-opacity"
          style={{ color: "var(--text-secondary)" }}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="mb-5">
          <h2
            className="text-xl font-bold mb-1"
            style={{ color: "var(--text-primary)" }}
          >
            Company Already Processed
          </h2>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {duplicates.length === 1
              ? `${duplicates[0].company_name} (${duplicates[0].domain})`
              : `${duplicates.length} companies`}{" "}
            already exist{duplicates.length === 1 ? "s" : ""} in the database.
          </p>
          {duplicates.length > 1 && (
            <ul className="mt-2 space-y-1">
              {duplicates.map((d) => (
                <li
                  key={d.domain}
                  className="text-xs font-mono px-2 py-1 rounded"
                  style={{
                    backgroundColor: "var(--bg-hover)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {d.company_name} — {d.domain}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Options */}
        <div className="space-y-3">
          {/* Incremental */}
          <button
            onClick={onIncremental}
            className="w-full flex items-start gap-4 p-4 rounded-xl text-left transition-all hover:scale-[1.01]"
            style={{
              backgroundColor: "rgba(152, 234, 101, 0.06)",
              border: "1px solid var(--brand-green)",
            }}
          >
            <div
              className="p-2 rounded-lg mt-0.5"
              style={{ backgroundColor: "rgba(152, 234, 101, 0.12)" }}
            >
              <Zap className="w-5 h-5" style={{ color: "var(--brand-green)" }} />
            </div>
            <div>
              <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                Incremental Update
              </p>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                Only re-extracts low-confidence and missing fields. Faster &amp; cheaper.
              </p>
            </div>
          </button>

          {/* From Scratch */}
          <button
            onClick={onScratch}
            className="w-full flex items-start gap-4 p-4 rounded-xl text-left transition-all hover:scale-[1.01]"
            style={{
              backgroundColor: "var(--bg-hover)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <div
              className="p-2 rounded-lg mt-0.5"
              style={{ backgroundColor: "var(--bg-card)" }}
            >
              <RefreshCw className="w-5 h-5" style={{ color: "var(--text-secondary)" }} />
            </div>
            <div>
              <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                Start from Scratch
              </p>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                Full re-run — replaces all existing data for this company.
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
