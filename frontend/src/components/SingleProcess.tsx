"use client";

import { useState } from "react";
import {
  Play,
  Loader2,
  CheckCircle,
  AlertCircle,
  Search,
  FileText,
  Database,
  ArrowRight,
} from "lucide-react";
import DuplicateDialog from "./DuplicateDialog";

interface SingleProcessProps {
  apiUrl: string;
  onViewResults: () => void;
  onViewCompany?: (company: Record<string, unknown>) => void;
}

interface PipelineStep {
  id: string;
  name: string;
  status: "pending" | "running" | "completed" | "error";
  message: string;
}

export default function SingleProcess({
  apiUrl,
  onViewResults,
}: SingleProcessProps) {
  const [companyName, setCompanyName] = useState("");
  const [domain, setDomain] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [steps, setSteps] = useState<PipelineStep[]>([
    { id: "search", name: "Web Search", status: "pending", message: "" },
    { id: "scrape", name: "Scraping", status: "pending", message: "" },
    { id: "extract", name: "Data Extraction", status: "pending", message: "" },
    { id: "validate", name: "Validation", status: "pending", message: "" },
    { id: "save", name: "Save Results", status: "pending", message: "" },
  ]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateSteps = (status: string) => {
    setSteps((prev) => {
      const newSteps = [...prev];

      if (status === "running") {
        const runningStep = newSteps.find((s) => s.status === "pending");
        if (runningStep) {
          runningStep.status = "running";
        }
      } else if (status === "completed") {
        newSteps.forEach((step) => {
          if (step.status === "running" || step.status === "pending") {
            step.status = "completed";
          }
        });
      }

      return newSteps;
    });
  };

  const pollJobStatus = async (domainToWatch: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${apiUrl}/company/${domainToWatch}`);
        if (response.ok) {
          updateSteps("completed");
          clearInterval(interval);
          setIsRunning(false);
          onViewResults();
        } else if (response.status === 404) {
          // Still processing — advance steps visually
          updateSteps("running");
        }
      } catch {
        // Network hiccup — keep polling
      }
    }, 2000);

    return () => clearInterval(interval);
  };

  const startRun = async (endpoint: "run" | "incremental") => {
    setShowDuplicateDialog(false);
    setError(null);
    setIsRunning(true);
    setSteps((prev) =>
      prev.map((s) => ({ ...s, status: "pending" as const, message: "" }))
    );
    try {
      const response = await fetch(`${apiUrl}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_name: companyName, domain }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to start processing");
      }
      const data = await response.json();
      setJobId(data.job_id);
      pollJobStatus(domain.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start processing");
      setIsRunning(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Check if company already exists in DB
    try {
      const res = await fetch(`${apiUrl}/company/${domain.trim()}`);
      if (res.ok) {
        setShowDuplicateDialog(true);
        return;
      }
    } catch {
      // If check fails, proceed normally
    }
    startRun("run");
  };

  const isFormValid = companyName.trim() !== "" && domain.trim() !== "";

  return (
    <div className="animate-fade-in page-container py-8">
      {showDuplicateDialog && (
        <DuplicateDialog
          duplicates={[{ company_name: companyName, domain }]}
          onIncremental={() => startRun("incremental")}
          onScratch={() => startRun("run")}
          onCancel={() => setShowDuplicateDialog(false)}
        />
      )}
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Page Header */}
        <div className="text-center mb-12">
          <h1
            className="text-3xl font-bold mb-4"
            style={{ color: "var(--text-primary)" }}
          >
            Single Company Processing
          </h1>
          <p
            className="text-lg"
            style={{ color: "var(--text-secondary)" }}
          >
            Extract comprehensive data for a single company
          </p>
        </div>

        {/* Input Form */}
        {!isRunning && !jobId && (
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div
                  className="flex items-start gap-3 px-4 py-4 rounded-lg"
                  style={{
                    backgroundColor: "rgba(255, 107, 107, 0.08)",
                    border: "1px solid rgba(255, 107, 107, 0.2)",
                    color: "var(--brand-red)",
                  }}
                >
                  <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-sm">Error</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                      {error}
                    </p>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label
                    htmlFor="companyName"
                    className="block text-sm font-medium mb-2"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    Company Name
                  </label>
                  <input
                    type="text"
                    id="companyName"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="e.g., Securitize"
                    className="input-brand"
                    disabled={isRunning}
                  />
                </div>

                <div>
                  <label
                    htmlFor="domain"
                    className="block text-sm font-medium mb-2"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    Domain
                  </label>
                  <input
                    type="text"
                    id="domain"
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    placeholder="e.g., securitize.io"
                    className="input-brand"
                    disabled={isRunning}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={!isFormValid || isRunning}
                className="btn-brand w-full flex items-center justify-center gap-2 py-3.5 text-base"
              >
                <Play className="w-5 h-5" />
                <span>Start Intelligence Pipeline</span>
              </button>
            </form>
          </div>
        )}

        {/* Pipeline Progress */}
        {(isRunning || jobId) && (
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <h2
              className="text-2xl font-bold mb-8"
              style={{ color: "var(--text-primary)" }}
            >
              Pipeline Progress
            </h2>

            <div className="space-y-4">
              {steps.map((step, index) => (
                <div key={step.id} className="flex items-center gap-4">
                  <div className="flex-shrink-0">
                    {step.status === "pending" && (
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center"
                        style={{
                          border: "2px solid var(--border-default)",
                          backgroundColor: "var(--surface)",
                        }}
                      >
                        <span
                          className="text-xs font-medium"
                          style={{ color: "var(--text-faint)" }}
                        >
                          {index + 1}
                        </span>
                      </div>
                    )}
                    {step.status === "running" && (
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center animate-pulse"
                        style={{
                          backgroundColor: "var(--brand-glow)",
                          border: "1px solid rgba(10, 6, 229, 0.3)",
                        }}
                      >
                        <Loader2
                          className="w-4 h-4 animate-spin"
                          style={{ color: "var(--brand)" }}
                        />
                      </div>
                    )}
                    {step.status === "completed" && (
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center"
                        style={{
                          backgroundColor: "rgba(152, 234, 101, 0.1)",
                          border: "1px solid rgba(152, 234, 101, 0.3)",
                        }}
                      >
                        <CheckCircle
                          className="w-4 h-4"
                          style={{ color: "var(--brand-green)" }}
                        />
                      </div>
                    )}
                    {step.status === "error" && (
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center"
                        style={{
                          backgroundColor: "rgba(255, 107, 107, 0.1)",
                          border: "1px solid rgba(255, 107, 107, 0.3)",
                        }}
                      >
                        <AlertCircle
                          className="w-4 h-4"
                          style={{ color: "var(--brand-red)" }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="flex-1 pt-1">
                    <p
                      className="font-semibold text-sm"
                      style={{
                        color:
                          step.status === "running"
                            ? "var(--brand-light)"
                            : step.status === "completed"
                            ? "var(--brand-green)"
                            : step.status === "error"
                            ? "var(--brand-red)"
                            : "var(--text-muted)",
                      }}
                    >
                      {step.name}
                    </p>
                    {step.message && (
                      <p
                        className="text-sm mt-1"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {step.message}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {jobId && (
              <div
                className="mt-8 pt-6 flex justify-between items-center"
                style={{ borderTop: "1px solid var(--border-faint)" }}
              >
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Job ID:{" "}
                  <code
                    className="px-2 py-0.5 rounded text-xs"
                    style={{
                      backgroundColor: "var(--brand-glow)",
                      color: "var(--brand-light)",
                      fontFamily: "var(--font-ibm-plex-mono)",
                    }}
                  >
                    {jobId}
                  </code>
                </p>
              </div>
            )}
          </div>
        )}

        {/* Quick Stats */}
        {jobId && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div
              className="rounded-xl p-5 flex items-center gap-4"
              style={{
                backgroundColor: "var(--elevated)",
                border: "1px solid var(--border-faint)",
              }}
            >
              <div
                className="p-3 rounded-lg"
                style={{ backgroundColor: "rgba(88, 199, 247, 0.1)" }}
              >
                <Search
                  className="w-5 h-5"
                  style={{ color: "var(--brand-light)" }}
                />
              </div>
              <div>
                <p
                  className="text-sm mb-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  Sources Explored
                </p>
                <p
                  className="text-2xl font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  ~160
                </p>
              </div>
            </div>

            <div
              className="rounded-xl p-5 flex items-center gap-4"
              style={{
                backgroundColor: "var(--elevated)",
                border: "1px solid var(--border-faint)",
              }}
            >
              <div
                className="p-3 rounded-lg"
                style={{ backgroundColor: "var(--brand-glow)" }}
              >
                <FileText
                  className="w-5 h-5"
                  style={{ color: "var(--brand)" }}
                />
              </div>
              <div>
                <p
                  className="text-sm mb-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  Fields Extracted
                </p>
                <p
                  className="text-2xl font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  303
                </p>
              </div>
            </div>

            <div
              className="rounded-xl p-5 flex items-center gap-4"
              style={{
                backgroundColor: "var(--elevated)",
                border: "1px solid var(--border-faint)",
              }}
            >
              <div
                className="p-3 rounded-lg"
                style={{ backgroundColor: "rgba(152, 234, 101, 0.1)" }}
              >
                <Database
                  className="w-5 h-5"
                  style={{ color: "var(--brand-green)" }}
                />
              </div>
              <div>
                <p
                  className="text-sm mb-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  Data Tables
                </p>
                <p
                  className="text-2xl font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  17
                </p>
              </div>
            </div>
          </div>
        )}

        {/* View Results Link */}
        {jobId && !isRunning && (
          <div className="text-center mt-8">
            <button onClick={onViewResults} className="btn-brand">
              <span>View Full Intelligence Report</span>
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
