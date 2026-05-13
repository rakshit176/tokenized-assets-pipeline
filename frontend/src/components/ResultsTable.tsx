"use client";

import { useState } from "react";
import {
  Search,
  ExternalLink,
  Filter,
  Download,
  RefreshCw,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  Loader2,
} from "lucide-react";

interface ResultsTableProps {
  apiUrl: string;
  onViewCompany: (company: Record<string, unknown>) => void;
  onNewProcess: () => void;
}

interface Company {
  id: number;
  company_name: string;
  domain: string;
  created_at: string;
  status: string;
  fill_rate?: number;
  total_cost_usd?: number;
  processing_time_seconds?: number;
  data?: Record<string, unknown>;
}

type SortBy = "created_at" | "company_name" | "fill_rate" | "cost";
type StatusFilter = "all" | "completed" | "failed" | "processing";

export default function ResultsTable({
  apiUrl,
  onViewCompany,
  onNewProcess,
}: ResultsTableProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchCompanies = async () => {
    setIsLoading(true);
    setError(false);
    try {
      const response = await fetch(`${apiUrl}/companies`);
      if (!response.ok) throw new Error("Failed to fetch");
      const data = await response.json();
      setCompanies(data);
    } catch {
      setError(true);
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch on mount and periodically
  useState(() => {
    fetchCompanies();
    const interval = setInterval(fetchCompanies, 10000);
    return () => clearInterval(interval);
  });

  const filteredAndSortedCompanies = companies
    .filter((company) => {
      const matchesSearch =
        company.company_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        company.domain.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus =
        statusFilter === "all" ||
        company.status.toLowerCase() === statusFilter;
      return matchesSearch && matchesStatus;
    })
    .sort((a, b) => {
      let comparison = 0;
      if (sortBy === "created_at") {
        comparison =
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      } else if (sortBy === "company_name") {
        comparison = a.company_name.localeCompare(b.company_name);
      } else if (sortBy === "fill_rate") {
        comparison = (a.fill_rate || 0) - (b.fill_rate || 0);
      } else if (sortBy === "cost") {
        comparison =
          (a.total_cost_usd || 0) - (b.total_cost_usd || 0);
      }
      return sortOrder === "asc" ? comparison : -comparison;
    });

  const stats = {
    total: companies.length,
    completed: companies.filter((c) => c.status === "completed").length,
    failed: companies.filter((c) => c.status === "failed").length,
    processing: companies.filter((c) => c.status === "processing").length,
    avgFillRate:
      companies.length > 0
        ? companies.reduce((sum, c) => sum + (c.fill_rate || 0), 0) /
          companies.length
        : 0,
    totalCost: companies.reduce(
      (sum, c) => sum + (c.total_cost_usd || 0),
      0
    ),
  };

  const handleSort = (column: SortBy) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
  };

  const SortIcon = ({ column }: { column: SortBy }) => {
    if (sortBy !== column)
      return <ArrowUpDown className="w-3 h-3 ml-1 opacity-40" />;
    return sortOrder === "asc" ? (
      <ChevronUp className="w-3 h-3 ml-1" style={{ color: "var(--brand-light)" }} />
    ) : (
      <ChevronDown className="w-3 h-3 ml-1" style={{ color: "var(--brand-light)" }} />
    );
  };

  const exportCSV = () => {
    const headers = [
      "Company Name",
      "Domain",
      "Status",
      "Fill Rate",
      "Cost (USD)",
      "Created At",
    ];
    const rows = filteredAndSortedCompanies.map((c) => [
      c.company_name,
      c.domain,
      c.status,
      c.fill_rate ? `${(c.fill_rate * 100).toFixed(1)}%` : "N/A",
      c.total_cost_usd ? `$${c.total_cost_usd.toFixed(6)}` : "N/A",
      new Date(c.created_at).toLocaleString(),
    ]);
    const csvContent = [headers, ...rows].map((row) => row.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `companies-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
  };

  const statusBadge = (status: string) => {
    if (status === "completed") return "badge-green";
    if (status === "failed") return "badge-red";
    return "badge-blue";
  };

  return (
    <div className="animate-fade-in page-container py-8">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1
              className="text-4xl font-bold"
              style={{ color: "var(--text-primary)" }}
            >
              Results Dashboard
            </h1>
            <p
              className="text-lg mt-2"
              style={{ color: "var(--text-secondary)" }}
            >
              View and manage all processed companies
            </p>
          </div>
          <button onClick={onNewProcess} className="btn-brand">
            New Intelligence Process
          </button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[
            { label: "Total", value: stats.total, color: "var(--text-primary)" },
            {
              label: "Completed",
              value: stats.completed,
              color: "var(--brand-green)",
              border: "var(--brand-green)",
            },
            {
              label: "Failed",
              value: stats.failed,
              color: "var(--brand-red)",
              border: "var(--brand-red)",
            },
            {
              label: "Processing",
              value: stats.processing,
              color: "var(--brand-light)",
              border: "var(--brand-light)",
            },
            {
              label: "Avg Fill Rate",
              value: `${(stats.avgFillRate * 100).toFixed(0)}%`,
              color: "var(--text-primary)",
            },
            {
              label: "Total Cost",
              value: `$${stats.totalCost.toFixed(4)}`,
              color: "var(--text-primary)",
            },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl p-4"
              style={{
                backgroundColor: "var(--elevated)",
                border: "1px solid var(--border-faint)",
                borderBottom: stat.border
                  ? `2px solid ${stat.border}`
                  : "1px solid var(--border-faint)",
              }}
            >
              <p
                className="text-sm mb-1"
                style={{ color: "var(--text-muted)" }}
              >
                {stat.label}
              </p>
              <p
                className="text-2xl font-bold"
                style={{
                  color: stat.color,
                  fontFamily: "var(--font-sora)",
                }}
              >
                {stat.value}
              </p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div
          className="rounded-xl p-4"
          style={{
            backgroundColor: "var(--elevated)",
            border: "1px solid var(--border-faint)",
          }}
        >
          <div className="flex flex-wrap gap-3 items-center">
            <div className="flex-1 min-w-[220px]">
              <div className="relative">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  type="text"
                  placeholder="Search companies..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="input-brand pl-9 py-2"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Filter
                className="w-4 h-4"
                style={{ color: "var(--text-muted)" }}
              />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="input-brand py-2 pr-8"
                style={{ appearance: "auto" }}
              >
                <option value="all">All Status</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="processing">Processing</option>
              </select>
            </div>

            <button
              onClick={exportCSV}
              className="btn-brand-outline flex items-center gap-2 py-2"
            >
              <Download className="w-4 h-4" />
              <span>Export</span>
            </button>

            <button
              onClick={fetchCompanies}
              className="btn-brand-outline flex items-center gap-2 py-2"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Results Table */}
        <div
          className="rounded-xl overflow-hidden"
          style={{
            backgroundColor: "var(--elevated)",
            border: "1px solid var(--border-faint)",
          }}
        >
          {isLoading ? (
            <div
              className="p-12 text-center animate-pulse"
              style={{ color: "var(--text-muted)" }}
            >
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-3" />
              Loading companies intelligence...
            </div>
          ) : error ? (
            <div
              className="p-12 text-center"
              style={{
                color: "var(--brand-red)",
                backgroundColor: "rgba(255, 107, 107, 0.05)",
              }}
            >
              Error loading companies. Please try again.
            </div>
          ) : filteredAndSortedCompanies.length === 0 ? (
            <div
              className="p-12 text-center"
              style={{ color: "var(--text-muted)" }}
            >
              No companies found. Start a new process to generate intelligence.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead
                  style={{
                    backgroundColor: "var(--elevated-2)",
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  <tr>
                    <th
                      onClick={() => handleSort("company_name")}
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors flex items-center"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Company
                      <SortIcon column="company_name" />
                    </th>
                    <th
                      onClick={() => handleSort("created_at")}
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span className="flex items-center">
                        Created
                        <SortIcon column="created_at" />
                      </span>
                    </th>
                    <th
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Status
                    </th>
                    <th
                      onClick={() => handleSort("fill_rate")}
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span className="flex items-center">
                        Fill Rate
                        <SortIcon column="fill_rate" />
                      </span>
                    </th>
                    <th
                      onClick={() => handleSort("cost")}
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span className="flex items-center">
                        Cost
                        <SortIcon column="cost" />
                      </span>
                    </th>
                    <th
                      className="px-5 py-4 text-xs font-semibold uppercase tracking-wider"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAndSortedCompanies.map((company) => (
                    <tr
                      key={company.id}
                      className="transition-colors"
                      style={{ borderBottom: "1px solid var(--border-faint)" }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor =
                          "var(--elevated-2)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                      }}
                    >
                      <td className="px-5 py-4">
                        <div>
                          <p
                            className="font-semibold text-sm"
                            style={{ color: "var(--text-primary)" }}
                          >
                            {company.company_name}
                          </p>
                          <p
                            className="text-sm mt-0.5"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {company.domain}
                          </p>
                        </div>
                      </td>
                      <td
                        className="px-5 py-4 text-sm"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {new Date(company.created_at).toLocaleDateString()}{" "}
                        <span style={{ color: "var(--text-faint)" }}>
                          {new Date(company.created_at).toLocaleTimeString()}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className={statusBadge(company.status)}>
                          {company.status}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        {company.fill_rate !== undefined ? (
                          <div className="flex items-center gap-2.5">
                            <div
                              className="w-16 rounded-full h-1.5 overflow-hidden"
                              style={{
                                backgroundColor: "var(--elevated-2)",
                              }}
                            >
                              <div
                                className="h-full rounded-full"
                                style={{
                                  backgroundColor: "var(--brand)",
                                  width: `${company.fill_rate * 100}%`,
                                  boxShadow:
                                    "0 0 8px var(--brand-glow)",
                                }}
                              />
                            </div>
                            <span
                              className="text-sm font-medium"
                              style={{
                                color: "var(--text-primary)",
                                fontFamily: "var(--font-ibm-plex-mono)",
                              }}
                            >
                              {(company.fill_rate * 100).toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span
                            className="text-sm"
                            style={{ color: "var(--text-faint)" }}
                          >
                            -
                          </span>
                        )}
                      </td>
                      <td
                        className="px-5 py-4 text-sm"
                        style={{
                          color: "var(--text-secondary)",
                          fontFamily: "var(--font-ibm-plex-mono)",
                        }}
                      >
                        {company.total_cost_usd
                          ? `$${company.total_cost_usd.toFixed(6)}`
                          : "-"}
                      </td>
                      <td className="px-5 py-4">
                        <button
                          onClick={() => onViewCompany(company)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all"
                          style={{
                            color: "var(--brand-light)",
                            backgroundColor: "var(--brand-glow)",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = "var(--brand)";
                            e.currentTarget.style.color = "#ffffff";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor =
                              "var(--brand-glow)";
                            e.currentTarget.style.color = "var(--brand-light)";
                          }}
                        >
                          <span>Details</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
