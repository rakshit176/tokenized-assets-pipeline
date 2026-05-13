"use client";

import { useState, useCallback, type MouseEvent } from "react";
import {
  Upload,
  Loader2,
  Play,
  CheckCircle,
  AlertCircle,
  X,
  FileSpreadsheet,
} from "lucide-react";
import DuplicateDialog from "./DuplicateDialog";

interface BatchProcessProps {
  apiUrl: string;
  onViewResults: () => void;
  onViewCompany?: (company: Record<string, unknown>) => void;
}

interface CompanyRow {
  company_name: string;
  domain: string;
  status: "pending" | "processing" | "completed" | "error";
  job_id?: string;
  error?: string;
  fill_rate?: number;
  cost_usd?: number;
}

interface ParsedCompany {
  company_name: string;
  domain: string;
  valid: boolean;
  error: string;
}

export default function BatchProcess({
  apiUrl,
  onViewResults,
}: BatchProcessProps) {
  const [companies, setCompanies] = useState<CompanyRow[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [duplicates, setDuplicates] = useState<{ company_name: string; domain: string }[]>([]);
  const [pendingMode, setPendingMode] = useState<"run" | "incremental" | null>(null);
  const [globalStatus, setGlobalStatus] = useState<
    "idle" | "processing" | "completed" | "error"
  >("idle");
  const [globalError, setGlobalError] = useState<string | null>(null);

  const parseCSV = useCallback((text: string): ParsedCompany[] => {
    const lines = text.split("\n");
    const parsed: ParsedCompany[] = [];

    let headerIndex = -1;
    lines.forEach((line, index) => {
      if (
        line.toLowerCase().includes("company") &&
        line.toLowerCase().includes("domain")
      ) {
        headerIndex = index;
      }
    });

    if (headerIndex === -1) {
      headerIndex = 0;
    }

    for (let i = headerIndex + 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = line.split(",");
      if (parts.length >= 2) {
        const company_name = parts[0]?.trim() || "";
        const domain = parts[1]?.trim() || "";

        if (company_name && domain) {
          parsed.push({
            company_name,
            domain,
            valid: domain.includes(".") && !domain.includes(" "),
            error: !domain.includes(".") ? "Invalid domain format" : "",
          });
        }
      }
    }

    return parsed;
  }, []);

  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target?.result as string;
        const parsed = parseCSV(text);

        setCompanies(
          parsed.map((p) => ({
            company_name: p.company_name,
            domain: p.domain,
            status: p.valid ? ("pending" as const) : ("error" as const),
            error: p.error || "",
          }))
        );
      };
      reader.readAsText(file);
    },
    [parseCSV]
  );

  const addCompany = () => {
    setCompanies((prev) => [
      ...prev,
      { company_name: "", domain: "", status: "pending" as const },
    ]);
  };

  const updateCompany = (index: number, updates: Partial<CompanyRow>) => {
    setCompanies((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...updates } : c))
    );
  };

  const removeCompany = (index: number) => {
    setCompanies((prev) => prev.filter((_, i) => i !== index));
  };

  const validateBatch = useCallback(() => {
    const validCompanies = companies.filter((c) => c.status !== "error");
    if (validCompanies.length === 0) {
      setGlobalError("No valid companies to process");
      return false;
    }

    const hasDuplicates = new Set<string>();
    for (const c of validCompanies) {
      const key = `${c.company_name}:${c.domain}`;
      if (hasDuplicates.has(key)) {
        setGlobalError(`Duplicate company: ${c.company_name}`);
        return false;
      }
      hasDuplicates.add(key);
    }

    return true;
  }, [companies]);

  const startBatch = async (mode: "run" | "incremental") => {
    setDuplicates([]);
    setPendingMode(null);
    setIsProcessing(true);
    setGlobalStatus("processing");
    setGlobalError(null);

    const validCompanies = companies.filter((c) => c.status !== "error");

    try {
      // For incremental: call /incremental per company; for run: use /batch
      if (mode === "incremental") {
        for (const c of validCompanies) {
          await fetch(`${apiUrl}/incremental`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name: c.company_name, domain: c.domain, timeout: 180 }),
          });
        }
        pollBatchResults(validCompanies);
        return;
      }

      const response = await fetch(`${apiUrl}/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companies: validCompanies.map((c) => ({
            company_name: c.company_name,
            domain: c.domain,
            timeout: 180,
          })),
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Batch processing failed");
      }

      const data = await response.json();

      // Update companies with job IDs — API returns { jobs: [...] }
      (data.jobs ?? data).forEach((result: { company_name: string; domain: string; job_id: string }) => {
        const companyIndex = companies.findIndex(
          (c) =>
            c.company_name === result.company_name &&
            c.domain === result.domain
        );
        if (companyIndex !== -1) {
          updateCompany(companyIndex, {
            status: "processing",
            job_id: result.job_id,
          });
        }
      });

      pollBatchResults(validCompanies);
    } catch (err) {
      setGlobalStatus("error");
      setGlobalError(
        err instanceof Error ? err.message : "Batch processing failed"
      );
      setIsProcessing(false);
    }
  };

  const pollBatchResults = (submittedCompanies?: CompanyRow[]) => {
    const toWatch = submittedCompanies ?? companies.filter((c) => c.status !== "error");
    const done = new Set<string>();

    const interval = setInterval(async () => {
      const pending = toWatch.filter((c) => !done.has(c.domain));

      if (pending.length === 0) {
        clearInterval(interval);
        setIsProcessing(false);
        setGlobalStatus("completed");
        return;
      }

      for (const company of pending) {
        try {
          const response = await fetch(`${apiUrl}/company/${company.domain}`);
          if (response.ok) {
            const data = await response.json();
            done.add(company.domain);
            setCompanies((prev) =>
              prev.map((c) =>
                c.domain === company.domain
                  ? { ...c, status: "completed" as const, fill_rate: data.fill_rate ?? undefined }
                  : c
              )
            );
          }
          // 404 means still processing — keep polling
        } catch {
          // Network hiccup — keep polling
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  };

  const completedCount = companies.filter((c) => c.status === "completed").length;
  const errorCount = companies.filter((c) => c.status === "error").length;
  const totalCost = companies.reduce((sum, c) => sum + (c.cost_usd || 0), 0);

  const canStartProcessing =
    !isProcessing &&
    companies.length > 0 &&
    companies.filter((c) => c.status !== "error").length > 0;

  const handleProcessBatch = async () => {
    if (!validateBatch()) return;
    const validCompanies = companies.filter((c) => c.status !== "error");
    const found: { company_name: string; domain: string }[] = [];
    for (const c of validCompanies) {
      try {
        const res = await fetch(`${apiUrl}/company/${c.domain.trim()}`);
        if (res.ok) found.push({ company_name: c.company_name, domain: c.domain });
      } catch {
        // proceed if check fails
      }
    }
    if (found.length > 0) {
      setDuplicates(found);
      return;
    }
    startBatch("run");
  };

  return (
    <div className="animate-fade-in page-container py-8">
      {duplicates.length > 0 && (
        <DuplicateDialog
          duplicates={duplicates}
          onIncremental={() => { setDuplicates([]); startBatch("incremental"); }}
          onScratch={() => { setDuplicates([]); startBatch("run"); }}
          onCancel={() => setDuplicates([])}
        />
      )}
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Page Header */}
        <div className="text-center mb-12">
          <h1
            className="text-4xl font-bold mb-4"
            style={{ color: "var(--text-primary)" }}
          >
            Batch Intelligence
          </h1>
          <p className="text-lg" style={{ color: "var(--text-secondary)" }}>
            Upload a CSV file or add companies manually for bulk processing
          </p>
        </div>

        {/* Global Error */}
        {globalError && (
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
                {globalError}
              </p>
            </div>
          </div>
        )}

        {/* CSV Upload */}
        {!isProcessing && globalStatus === "idle" && (
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <div className="mb-6">
              <label
                htmlFor="csvUpload"
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer transition-colors"
                style={{
                  borderColor: "var(--border-subtle)",
                  backgroundColor: "rgba(10, 10, 10, 0.5)",
                }}
                onMouseEnter={(e: MouseEvent<HTMLLabelElement>) => {
                  e.currentTarget.style.borderColor = "var(--brand)";
                  e.currentTarget.style.backgroundColor = "var(--brand-glow)";
                }}
                onMouseLeave={(e: MouseEvent<HTMLLabelElement>) => {
                  e.currentTarget.style.borderColor = "var(--border-subtle)";
                  e.currentTarget.style.backgroundColor = "rgba(10, 10, 10, 0.5)";
                }}
              >
                <Upload
                  className="w-8 h-8 mb-2"
                  style={{ color: "var(--text-muted)" }}
                />
                <span className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Click to upload CSV file (format: company_name, domain)
                </span>
                <input
                  id="csvUpload"
                  type="file"
                  accept=".csv"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>

            {/* Companies List */}
            {companies.length > 0 && (
              <>
                <div
                  className="pt-6"
                  style={{ borderTop: "1px solid var(--border-faint)" }}
                >
                  <div className="flex justify-between items-center mb-4">
                    <h3
                      className="text-xl font-bold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      Companies ({companies.length})
                    </h3>
                    <button
                      type="button"
                      onClick={addCompany}
                      className="text-sm font-medium transition-colors"
                      style={{ color: "var(--brand-light)" }}
                      onMouseEnter={(e: MouseEvent<HTMLButtonElement>) => {
                        e.currentTarget.style.color = "var(--brand)";
                      }}
                      onMouseLeave={(e: MouseEvent<HTMLButtonElement>) => {
                        e.currentTarget.style.color = "var(--brand-light)";
                      }}
                    >
                      + Add Company
                    </button>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr
                          style={{
                            borderBottom: "1px solid var(--border-subtle)",
                          }}
                        >
                          <th
                            className="px-4 py-3 text-xs font-semibold uppercase"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Company
                          </th>
                          <th
                            className="px-4 py-3 text-xs font-semibold uppercase"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Domain
                          </th>
                          <th
                            className="px-4 py-3 text-xs font-semibold uppercase"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Status
                          </th>
                          <th
                            className="px-4 py-3 text-xs font-semibold uppercase"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Fill Rate
                          </th>
                          <th
                            className="px-4 py-3 text-xs font-semibold uppercase"
                            style={{ color: "var(--text-muted)" }}
                          >
                            Cost
                          </th>
                          <th className="px-4 py-3"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {companies.map((company, index) => (
                          <tr
                            key={index}
                            style={{
                              borderBottom: "1px solid var(--border-faint)",
                            }}
                          >
                            <td className="px-4 py-3">
                              <input
                                type="text"
                                value={company.company_name}
                                onChange={(e) =>
                                  updateCompany(index, {
                                    company_name: e.target.value,
                                  })
                                }
                                className="input-brand px-3 py-1.5 text-sm"
                                disabled={isProcessing}
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="text"
                                value={company.domain}
                                onChange={(e) =>
                                  updateCompany(index, {
                                    domain: e.target.value,
                                  })
                                }
                                className="input-brand px-3 py-1.5 text-sm"
                                disabled={isProcessing}
                              />
                            </td>
                            <td className="px-4 py-3">
                              {company.status === "pending" && (
                                <span
                                  className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium"
                                  style={{
                                    backgroundColor: "var(--elevated-2)",
                                    color: "var(--text-muted)",
                                    border: "1px solid var(--border-faint)",
                                  }}
                                >
                                  Pending
                                </span>
                              )}
                              {company.status === "processing" && (
                                <span className="badge-blue">
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                  Processing
                                </span>
                              )}
                              {company.status === "completed" && (
                                <span className="badge-green">
                                  <CheckCircle className="w-3 h-3" />
                                  {company.fill_rate
                                    ? `${(company.fill_rate * 100).toFixed(0)}%`
                                    : "Done"}
                                </span>
                              )}
                              {company.status === "error" && (
                                <span className="badge-red">
                                  <AlertCircle className="w-3 h-3" />
                                  {company.error || "Error"}
                                </span>
                              )}
                            </td>
                            <td
                              className="px-4 py-3 text-sm"
                              style={{
                                color: "var(--text-secondary)",
                                fontFamily: "var(--font-ibm-plex-mono)",
                              }}
                            >
                              {company.fill_rate
                                ? `${(company.fill_rate * 100).toFixed(0)}%`
                                : "-"}
                            </td>
                            <td
                              className="px-4 py-3 text-sm"
                              style={{
                                color: "var(--text-secondary)",
                                fontFamily: "var(--font-ibm-plex-mono)",
                              }}
                            >
                              {company.cost_usd
                                ? `$${company.cost_usd.toFixed(6)}`
                                : "-"}
                            </td>
                            <td className="px-4 py-3">
                              {company.status === "pending" && (
                                <button
                                  onClick={() => removeCompany(index)}
                                  className="transition-colors disabled:opacity-50 p-1 rounded"
                                  style={{ color: "var(--brand-red)" }}
                                  disabled={isProcessing}
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div
                  className="flex justify-end gap-3 pt-6 mt-6"
                  style={{ borderTop: "1px solid var(--border-faint)" }}
                >
                  <button
                    type="button"
                    onClick={() => setCompanies([])}
                    className="btn-brand-outline"
                  >
                    Clear All
                  </button>
                  <button
                    type="button"
                    onClick={handleProcessBatch}
                    disabled={!canStartProcessing}
                    className="btn-brand flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Play className="w-4 h-4" />
                    <span>Process Batch</span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Processing Status */}
        {isProcessing && globalStatus === "processing" && (
          <div
            className="rounded-xl p-8 text-center"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <div className="mb-6">
              <FileSpreadsheet
                className="w-12 h-12 mx-auto mb-4"
                style={{ color: "var(--brand)" }}
              />
              <h2
                className="text-2xl font-bold mb-2"
                style={{ color: "var(--text-primary)" }}
              >
                Processing Intelligence Batch
              </h2>
              <div
                className="flex items-center justify-center gap-2 text-lg"
                style={{ color: "var(--brand-light)" }}
              >
                <Loader2 className="w-5 h-5 animate-spin" />
                <span>
                  Analyzing{" "}
                  {companies.filter((c) => c.status === "processing").length} of{" "}
                  {companies.length} targets...
                </span>
              </div>
            </div>

            <div className="max-w-2xl mx-auto">
              <div
                className="w-full rounded-full h-2.5 overflow-hidden"
                style={{
                  backgroundColor: "var(--elevated-2)",
                  border: "1px solid var(--border-faint)",
                }}
              >
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    backgroundColor: "var(--brand)",
                    width: `${(completedCount / companies.length) * 100}%`,
                    boxShadow: "0 0 10px var(--brand-glow)",
                  }}
                />
              </div>
              <p
                className="text-sm mt-4"
                style={{ color: "var(--text-muted)" }}
              >
                {completedCount} of {companies.length} profiles successfully
                constructed
              </p>
            </div>
          </div>
        )}

        {/* Batch Complete */}
        {!isProcessing && globalStatus === "completed" && (
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-faint)",
            }}
          >
            <h2
              className="text-2xl font-bold mb-8 text-center"
              style={{ color: "var(--text-primary)" }}
            >
              Intelligence Batch Complete
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div
                className="p-6 rounded-xl text-center"
                style={{
                  backgroundColor: "rgba(152, 234, 101, 0.05)",
                  border: "1px solid rgba(152, 234, 101, 0.15)",
                }}
              >
                <p
                  className="text-4xl font-bold"
                  style={{ color: "var(--brand-green)" }}
                >
                  {completedCount}
                </p>
                <p
                  className="text-sm mt-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  Successfully Profiled
                </p>
              </div>
              <div
                className="p-6 rounded-xl text-center"
                style={{
                  backgroundColor: "rgba(255, 107, 107, 0.05)",
                  border: "1px solid rgba(255, 107, 107, 0.15)",
                }}
              >
                <p
                  className="text-4xl font-bold"
                  style={{ color: "var(--brand-red)" }}
                >
                  {errorCount}
                </p>
                <p
                  className="text-sm mt-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  Encountered Errors
                </p>
              </div>
              <div
                className="p-6 rounded-xl text-center"
                style={{
                  backgroundColor: "var(--elevated-2)",
                  border: "1px solid var(--border-faint)",
                }}
              >
                <p
                  className="text-4xl font-bold"
                  style={{
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-ibm-plex-mono)",
                  }}
                >
                  ${totalCost.toFixed(6)}
                </p>
                <p
                  className="text-sm mt-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  Total Processing Cost
                </p>
              </div>
            </div>

            <div className="flex justify-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setCompanies([]);
                  setGlobalStatus("idle");
                }}
                className="btn-brand-outline"
              >
                Clear Process
              </button>
              <button
                type="button"
                onClick={onViewResults}
                className="btn-brand"
              >
                View Full Results Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
