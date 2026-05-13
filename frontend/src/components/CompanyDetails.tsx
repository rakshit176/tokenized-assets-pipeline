"use client";

import { useState, useEffect } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Clock,
  DollarSign,
  CheckCircle,
  AlertCircle,
  Loader2,
  FileText,
  Globe,
  Linkedin,
  Twitter,
  Database,
  Download,
} from "lucide-react";

interface CompanyDetailsProps {
  apiUrl: string;
  onBack: () => void;
  companyDomain?: string;
  companyData?: Record<string, unknown>;
}

interface Source {
  url: string;
  title: string;
  type: string;
  retrieved_at: string;
}

interface FieldData {
  field_name: string;
  value: string | number | boolean | null;
  confidence: number;
  sources: string[];
}

interface CompanyInfo {
  id: number;
  company_name: string;
  domain: string;
  status: string;
  created_at: string;
  completed_at?: string;
  processing_time_seconds?: number;
  fill_rate?: number;
  total_cost_usd?: number;
  data?: Record<string, unknown>;
  sources?: Source[];
  fields?: FieldData[];
  errors?: string[];
}

export default function CompanyDetails({
  apiUrl,
  onBack,
  companyDomain,
  companyData,
}: CompanyDetailsProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "fields" | "sources">(
    "overview"
  );
  const [company, setCompany] = useState<CompanyInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const domain = companyDomain || (companyData as { domain?: string })?.domain;
    if (!domain) {
      setIsLoading(false);
      return;
    }

    const fetchCompany = async () => {
      setIsLoading(true);
      setHasError(false);
      try {
        const response = await fetch(`${apiUrl}/company/${domain}`);
        if (!response.ok) throw new Error("Failed to fetch");
        const data = await response.json();
        setCompany(data);
      } catch {
        // If API fails, try using the companyData passed in
        if (companyData) {
          setCompany(companyData as unknown as CompanyInfo);
        } else {
          setHasError(true);
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchCompany();
  }, [apiUrl, companyDomain, companyData]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2
          className="w-8 h-8 animate-spin"
          style={{ color: "var(--brand)" }}
        />
      </div>
    );
  }

  if (hasError || !company) {
    return (
      <div className="page-container py-8">
        <div className="max-w-5xl mx-auto">
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
              <p className="font-medium">Error</p>
              <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                Failed to load company details.
              </p>
            </div>
          </div>
          <button
            onClick={onBack}
            className="btn-brand-outline mt-4 flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: "overview" as const, label: "Overview", count: 0 },
    {
      id: "fields" as const,
      label: "Extracted Fields",
      count: company.fields?.length || 0,
    },
    {
      id: "sources" as const,
      label: "Sources",
      count: company.sources?.length || 0,
    },
  ];

  const categorizedFields =
    company.fields?.reduce(
      (acc, field) => {
        const category = field.field_name.split("_")[0] || "other";
        if (!acc[category]) acc[category] = [];
        acc[category].push(field);
        return acc;
      },
      {} as Record<string, FieldData[]>
    ) || {};

  const sourcesByType =
    company.sources?.reduce(
      (acc, source) => {
        if (!acc[source.type]) acc[source.type] = [];
        acc[source.type].push(source);
        return acc;
      },
      {} as Record<string, Source[]>
    ) || {};

  return (
    <div className="animate-fade-in page-container py-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--text-muted)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = "var(--elevated)";
                e.currentTarget.style.color = "var(--text-primary)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = "transparent";
                e.currentTarget.style.color = "var(--text-muted)";
              }}
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1
                className="text-3xl md:text-4xl font-bold"
                style={{ color: "var(--text-primary)" }}
              >
                {company.company_name}
              </h1>
              <p
                className="text-lg mt-1"
                style={{ color: "var(--text-secondary)" }}
              >
                {company.domain}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {company.status === "completed" && (
              <a
                href={`${apiUrl}/download/${company.domain}`}
                download
                className="btn-brand flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                <span>Download XLSX</span>
              </a>
            )}
            <a
              href={`https://${company.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-brand-outline flex items-center gap-2"
            >
              <Globe className="w-4 h-4" />
              <span>Visit Website</span>
            </a>
          </div>
        </div>

        {/* Status Banner */}
        <div
          className="rounded-xl p-5"
          style={{
            backgroundColor:
              company.status === "completed"
                ? "rgba(152, 234, 101, 0.04)"
                : company.status === "failed"
                ? "rgba(255, 107, 107, 0.04)"
                : "var(--brand-glow)",
            border: "1px solid var(--border-faint)",
            borderLeftWidth: "4px",
            borderLeftColor:
              company.status === "completed"
                ? "var(--brand-green)"
                : company.status === "failed"
                ? "var(--brand-red)"
                : "var(--brand)",
          }}
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              {company.status === "completed" ? (
                <div
                  className="p-2 rounded-full"
                  style={{
                    backgroundColor: "rgba(152, 234, 101, 0.15)",
                  }}
                >
                  <CheckCircle
                    className="w-7 h-7"
                    style={{ color: "var(--brand-green)" }}
                  />
                </div>
              ) : company.status === "failed" ? (
                <div
                  className="p-2 rounded-full"
                  style={{
                    backgroundColor: "rgba(255, 107, 107, 0.15)",
                  }}
                >
                  <AlertCircle
                    className="w-7 h-7"
                    style={{ color: "var(--brand-red)" }}
                  />
                </div>
              ) : (
                <div
                  className="p-2 rounded-full"
                  style={{ backgroundColor: "var(--brand-glow)" }}
                >
                  <Loader2
                    className="w-7 h-7 animate-spin"
                    style={{ color: "var(--brand-light)" }}
                  />
                </div>
              )}
              <div>
                <p
                  className="text-lg font-bold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {company.status === "completed"
                    ? "Intelligence Profile Complete"
                    : company.status === "failed"
                    ? "Processing Failed"
                    : "Gathering Intelligence..."}
                </p>
                <p
                  className="text-sm mt-1"
                  style={{ color: "var(--text-muted)" }}
                >
                  {company.completed_at
                    ? `Completed on ${new Date(company.completed_at).toLocaleString()}`
                    : `Started on ${new Date(company.created_at).toLocaleString()}`}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {company.processing_time_seconds != null && (
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                  style={{
                    backgroundColor: "var(--elevated-2)",
                    border: "1px solid var(--border-faint)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <Clock
                    className="w-4 h-4"
                    style={{ color: "var(--brand-light)" }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-ibm-plex-mono)",
                      fontSize: "0.875rem",
                    }}
                  >
                    {company.processing_time_seconds}s
                  </span>
                </div>
              )}
              {company.total_cost_usd != null && (
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                  style={{
                    backgroundColor: "var(--elevated-2)",
                    border: "1px solid var(--border-faint)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <DollarSign
                    className="w-4 h-4"
                    style={{ color: "var(--brand-green)" }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-ibm-plex-mono)",
                      fontSize: "0.875rem",
                    }}
                  >
                    ${company.total_cost_usd.toFixed(6)}
                  </span>
                </div>
              )}
              {company.fill_rate != null && (
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                  style={{
                    backgroundColor: "var(--elevated-2)",
                    border: "1px solid var(--border-faint)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <span
                    className="font-bold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {(company.fill_rate * 100).toFixed(0)}%
                  </span>
                  <span>fill rate</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ borderBottom: "1px solid var(--border-subtle)" }}>
          <nav className="flex gap-6">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="py-3 px-1 font-medium text-sm transition-colors flex items-center gap-2"
                style={{
                  borderBottom: activeTab === tab.id ? "2px solid var(--brand)" : "2px solid transparent",
                  color:
                    activeTab === tab.id
                      ? "var(--brand-light)"
                      : "var(--text-muted)",
                }}
                onMouseEnter={(e) => {
                  if (activeTab !== tab.id) {
                    e.currentTarget.style.color = "var(--text-primary)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (activeTab !== tab.id) {
                    e.currentTarget.style.color = "var(--text-muted)";
                  }
                }}
              >
                <span>{tab.label}</span>
                {tab.count > 0 && (
                  <span
                    className="px-2 py-0.5 rounded-full text-xs font-bold"
                    style={{
                      backgroundColor:
                        activeTab === tab.id
                          ? "var(--brand-glow)"
                          : "var(--elevated-2)",
                      color:
                        activeTab === tab.id
                          ? "var(--brand-light)"
                          : "var(--text-muted)",
                    }}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div
          className="rounded-xl overflow-hidden"
          style={{
            backgroundColor: "var(--elevated)",
            border: "1px solid var(--border-faint)",
          }}
        >
          {activeTab === "overview" && (
            <div className="p-6 space-y-8">
              {/* Company Info */}
              <div>
                <h3
                  className="text-xl font-bold mb-5"
                  style={{ color: "var(--text-primary)" }}
                >
                  Core Information
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { label: "Company Name", value: company.company_name },
                    { label: "Domain", value: company.domain },
                    {
                      label: "Status",
                      value: company.status.toUpperCase(),
                      isStatus: true,
                    },
                    {
                      label: "Created",
                      value: new Date(company.created_at).toLocaleString(),
                    },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="p-4 rounded-xl"
                      style={{
                        backgroundColor: "var(--elevated-2)",
                        border: "1px solid var(--border-faint)",
                      }}
                    >
                      <p
                        className="text-sm mb-1"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {item.label}
                      </p>
                      <p
                        className="text-lg font-bold"
                        style={{
                          color: item.isStatus
                            ? company.status === "completed"
                              ? "var(--brand-green)"
                              : "var(--brand-red)"
                            : "var(--text-primary)",
                        }}
                      >
                        {item.value}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Errors */}
              {company.errors && company.errors.length > 0 && (
                <div>
                  <h3
                    className="text-xl font-bold mb-4"
                    style={{ color: "var(--brand-red)" }}
                  >
                    Errors
                  </h3>
                  <div
                    className="rounded-xl p-5"
                    style={{
                      backgroundColor: "rgba(255, 107, 107, 0.05)",
                      border: "1px solid rgba(255, 107, 107, 0.15)",
                    }}
                  >
                    <ul className="space-y-3">
                      {company.errors.map((err, index) => (
                        <li
                          key={index}
                          className="flex items-start gap-3"
                          style={{ color: "var(--brand-red)" }}
                        >
                          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                          <span className="font-medium text-sm">{err}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Raw Data Preview */}
              {company.data && Object.keys(company.data).length > 0 && (
                <div>
                  <h3
                    className="text-xl font-bold mb-5"
                    style={{ color: "var(--text-primary)" }}
                  >
                    Raw Intelligence Payload
                  </h3>
                  <div
                    className="rounded-xl p-5 overflow-x-auto"
                    style={{
                      backgroundColor: "var(--surface)",
                      border: "1px solid var(--border-faint)",
                    }}
                  >
                    <pre
                      className="text-sm"
                      style={{
                        color: "var(--brand-light)",
                        fontFamily: "var(--font-ibm-plex-mono)",
                      }}
                    >
                      {JSON.stringify(company.data, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "fields" && (
            <div className="p-6">
              {company.fields && company.fields.length > 0 ? (
                <div className="space-y-8">
                  {Object.entries(categorizedFields).map(
                    ([category, fields]) => (
                      <div key={category}>
                        <h3
                          className="text-xl font-bold mb-5 capitalize pb-2"
                          style={{
                            color: "var(--brand-light)",
                            borderBottom: "1px solid var(--border-faint)",
                          }}
                        >
                          {category.replace(/_/g, " ")}
                        </h3>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {fields.map((field, index) => (
                            <div
                              key={index}
                              className="p-4 rounded-xl transition-colors group"
                              style={{
                                backgroundColor: "var(--elevated-2)",
                                border: "1px solid var(--border-faint)",
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.borderColor =
                                  "rgba(10, 6, 229, 0.3)";
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.borderColor =
                                  "var(--border-faint)";
                              }}
                            >
                              <div className="flex items-start justify-between">
                                <div className="flex-1">
                                  <div className="flex items-center gap-2 mb-2">
                                    <h4
                                      className="font-bold uppercase tracking-wide text-xs"
                                      style={{ color: "var(--text-primary)" }}
                                    >
                                      {field.field_name.replace(/_/g, " ")}
                                    </h4>
                                    {field.confidence != null && field.confidence > 0 && (
                                      <span
                                        className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
                                        style={{
                                          backgroundColor: "var(--brand-glow)",
                                          color: "var(--brand-light)",
                                        }}
                                      >
                                        {(field.confidence * 100).toFixed(0)}%
                                        CONF
                                      </span>
                                    )}
                                  </div>
                                  <p
                                    className="text-base font-medium"
                                    style={{ color: "var(--text-primary)" }}
                                  >
                                    {field.value === null || field.value === "" ? (
                                      <span
                                        className="italic"
                                        style={{ color: "var(--text-muted)" }}
                                      >
                                        Not found
                                      </span>
                                    ) : typeof field.value === "boolean" ? (
                                      field.value ? "Yes" : "No"
                                    ) : (
                                      String(field.value)
                                    )}
                                  </p>
                                </div>
                              </div>
                              {field.sources && field.sources.length > 0 && (
                                <div
                                  className="mt-3 pt-2 flex items-center gap-2 text-xs transition-colors"
                                  style={{
                                    borderTop: "1px solid var(--border-faint)",
                                    color: "var(--text-faint)",
                                  }}
                                >
                                  <FileText className="w-3.5 h-3.5" />
                                  <span>
                                    Derived from {field.sources.length} source(s)
                                  </span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <div
                  className="text-center py-16"
                  style={{ color: "var(--text-muted)" }}
                >
                  <Database
                    className="w-14 h-14 mx-auto mb-4 opacity-40"
                    style={{ color: "var(--brand)" }}
                  />
                  <p className="text-xl font-medium">No fields extracted yet.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === "sources" && (
            <div className="p-6">
              {company.sources && company.sources.length > 0 ? (
                <div className="space-y-8">
                  {Object.entries(sourcesByType).map(([type, sources]) => (
                    <div key={type}>
                      <h3
                        className="text-xl font-bold mb-5 capitalize pb-2"
                        style={{
                          color: "var(--brand-light)",
                          borderBottom: "1px solid var(--border-faint)",
                        }}
                      >
                        {type.replace(/_/g, " ")} Sources{" "}
                        <span
                          className="text-base"
                          style={{ color: "var(--text-muted)" }}
                        >
                          ({sources.length})
                        </span>
                      </h3>
                      <div className="space-y-2">
                        {sources.map((source, index) => (
                          <a
                            key={index}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between p-4 rounded-xl transition-all group"
                            style={{
                              backgroundColor: "var(--elevated-2)",
                              border: "1px solid var(--border-faint)",
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.backgroundColor =
                                "var(--brand-glow)";
                              e.currentTarget.style.borderColor =
                                "rgba(10, 6, 229, 0.3)";
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.backgroundColor =
                                "var(--elevated-2)";
                              e.currentTarget.style.borderColor =
                                "var(--border-faint)";
                            }}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <div
                                className="p-2.5 rounded-lg flex-shrink-0 transition-colors"
                                style={{
                                  backgroundColor: "var(--surface)",
                                  border: "1px solid var(--border-faint)",
                                }}
                              >
                                {source.type === "linkedin" ? (
                                  <Linkedin
                                    className="w-5 h-5"
                                    style={{ color: "#0A66C2" }}
                                  />
                                ) : source.type === "twitter" ? (
                                  <Twitter
                                    className="w-5 h-5"
                                    style={{ color: "#1DA1F2" }}
                                  />
                                ) : (
                                  <Globe
                                    className="w-5 h-5"
                                    style={{ color: "var(--brand-light)" }}
                                  />
                                )}
                              </div>
                              <div className="min-w-0">
                                <p
                                  className="font-bold text-sm truncate"
                                  style={{ color: "var(--text-primary)" }}
                                >
                                  {source.title || source.url}
                                </p>
                                <p
                                  className="text-xs truncate mt-0.5"
                                  style={{
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-ibm-plex-mono)",
                                  }}
                                >
                                  {source.url}
                                </p>
                              </div>
                            </div>
                            <ExternalLink
                              className="w-4 h-4 flex-shrink-0 ml-3 transition-colors"
                              style={{ color: "var(--text-faint)" }}
                            />
                          </a>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  className="text-center py-16"
                  style={{ color: "var(--text-muted)" }}
                >
                  <Globe
                    className="w-14 h-14 mx-auto mb-4 opacity-40"
                    style={{ color: "var(--brand-light)" }}
                  />
                  <p className="text-xl font-medium">No sources available.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
