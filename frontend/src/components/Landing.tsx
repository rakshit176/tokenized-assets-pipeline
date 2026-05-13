"use client";

import { useState } from "react";
import { Search, Zap, Database, Layers, ArrowRight, BarChart3, Shield, Globe } from "lucide-react";

interface LandingProps {
  onNavigate: (view: "single" | "batch" | "results" | "details") => void;
  onAnalyzeDomain: (domain: string) => void;
}

export default function Landing({ onNavigate, onAnalyzeDomain }: LandingProps) {
  const [domain, setDomain] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (domain.trim()) {
      onAnalyzeDomain(domain.trim());
    }
  };

  const features = [
    {
      icon: Zap,
      title: "Real-time Pipeline",
      description:
        "Powered by advanced worker queues to extract and process data from over 160 sources simultaneously without breaking a sweat.",
      color: "var(--brand)",
    },
    {
      icon: Database,
      title: "Deep Profiling",
      description:
        "Aggregates data into 17 distinct tables capturing financial metrics, key personnel, tech stacks, and regulatory compliance status.",
      color: "var(--brand-light)",
    },
    {
      icon: Layers,
      title: "Premium UI",
      description:
        "A visually striking interface designed for data scientists and analysts who demand performance wrapped in beautiful aesthetics.",
      color: "var(--brand-green)",
    },
  ];

  const capabilities = [
    {
      icon: BarChart3,
      title: "303+",
      subtitle: "Data Points Captured",
    },
    {
      icon: Zap,
      title: "< 5s",
      subtitle: "Real-time Processing",
    },
    {
      icon: Shield,
      title: "99%",
      subtitle: "Data Fill Rate",
    },
    {
      icon: Globe,
      title: "10x",
      subtitle: "Faster Research",
    },
  ];

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--bg)" }}>
      {/* Hero Background Glows */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] opacity-20 pointer-events-none overflow-hidden">
        <div
          className="absolute top-0 left-1/4 w-[400px] h-[400px] rounded-full mix-blend-screen animate-pulse"
          style={{ backgroundColor: "var(--brand)", filter: "blur(120px)" }}
        />
        <div
          className="absolute top-1/4 right-1/4 w-[300px] h-[300px] rounded-full mix-blend-screen opacity-60"
          style={{ backgroundColor: "var(--brand-light)", filter: "blur(100px)" }}
        />
      </div>

      {/* Hero Section */}
      <section className="relative min-h-[85vh] flex items-center justify-center pt-20 pb-32">
        <div className="page-container relative z-10 text-center">
          <div className="max-w-4xl mx-auto">
            {/* Tag */}
            <div
              className="inline-flex items-center gap-2 rounded-full px-4 py-2 mb-8"
              style={{
                backgroundColor: "rgba(10, 6, 229, 0.08)",
                border: "1px solid rgba(10, 6, 229, 0.2)",
              }}
            >
              <span
                className="w-2 h-2 rounded-full animate-pulse"
                style={{ backgroundColor: "var(--brand)" }}
              />
              <span
                className="text-sm font-medium"
                style={{ color: "var(--brand-light)" }}
              >
                FiftyOne Intelligence Platform
              </span>
            </div>

            {/* Headline */}
            <h1
              className="text-5xl md:text-7xl font-bold tracking-tight mb-8 leading-tight"
              style={{ color: "var(--text-primary)" }}
            >
              Unleash the Future of <br />
              <span
                className="text-transparent bg-clip-text"
                style={{
                  backgroundImage:
                    "linear-gradient(135deg, var(--brand), var(--brand-light))",
                }}
              >
                Company Intelligence
              </span>
            </h1>

            {/* Subheadline */}
            <p
              className="text-lg md:text-xl max-w-2xl mx-auto mb-12 leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              Advanced data gathering, deep profiling, and real-time intelligence
              for companies. Precision analytics wrapped in a stunning experience.
            </p>

            {/* Search Bar */}
            <form
              onSubmit={handleSubmit}
              className="relative max-w-2xl mx-auto mb-16 group"
            >
              <Search
                className="absolute left-5 top-1/2 -translate-y-1/2 h-5 w-5 pointer-events-none transition-colors"
                style={{ color: "var(--text-muted)" }}
              />
              <input
                type="text"
                placeholder="Analyze a company domain (e.g., securitize.io)"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                className="w-full rounded-full py-4 pl-12 pr-36 text-base transition-all input-brand"
                style={{
                  backgroundColor: "var(--elevated)",
                  border: "1px solid var(--border-subtle)",
                  boxShadow: "0 8px 30px rgba(0,0,0,0.3)",
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = "var(--brand)";
                  e.currentTarget.style.boxShadow =
                    "0 0 0 3px var(--brand-glow), 0 8px 30px rgba(0,0,0,0.3)";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = "var(--border-subtle)";
                  e.currentTarget.style.boxShadow =
                    "0 8px 30px rgba(0,0,0,0.3)";
                }}
                required
              />
              <button
                type="submit"
                className="absolute inset-y-2 right-2 btn-brand rounded-full flex items-center gap-2 py-2 px-5 text-sm"
              >
                <span>Analyze</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            {/* Quick Action Buttons */}
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => onNavigate("single")}
                className="btn-brand flex items-center gap-2"
              >
                <Zap className="w-4 h-4" />
                Single Analysis
              </button>
              <button
                onClick={() => onNavigate("batch")}
                className="btn-brand-outline flex items-center gap-2"
              >
                <Database className="w-4 h-4" />
                Batch Process
              </button>
              <button
                onClick={() => onNavigate("results")}
                className="btn-brand-outline flex items-center gap-2"
              >
                <BarChart3 className="w-4 h-4" />
                View Results
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section
        className="relative z-10 py-10"
        style={{
          borderTop: "1px solid var(--border-faint)",
          borderBottom: "1px solid var(--border-faint)",
          backgroundColor: "rgba(10, 10, 10, 0.5)",
        }}
      >
        <div className="page-container">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            {capabilities.map((cap, index) => (
              <div
                key={cap.subtitle}
                className="relative"
                style={{
                  borderRight:
                    index < capabilities.length - 1
                      ? "1px solid var(--border-faint)"
                      : "none",
                }}
              >
                <div
                  className="text-4xl font-bold mb-2"
                  style={{
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-sora)",
                  }}
                >
                  {cap.title}
                </div>
                <div
                  className="text-sm font-medium"
                  style={{ color: "var(--text-muted)" }}
                >
                  {cap.subtitle}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section
        className="relative z-10 py-24"
        style={{ backgroundColor: "var(--bg)" }}
      >
        <div className="page-container">
          <div className="text-center mb-16">
            <h2
              className="text-3xl md:text-4xl font-bold mb-4"
              style={{ color: "var(--text-primary)" }}
            >
              Intelligence at Scale
            </h2>
            <p
              className="max-w-2xl mx-auto"
              style={{ color: "var(--text-secondary)" }}
            >
              Everything you need to deeply understand the company landscape in
              one elegant platform.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="card-hover rounded-xl p-6"
                  style={{
                    backgroundColor: "var(--elevated)",
                    border: "1px solid var(--border-faint)",
                  }}
                >
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center mb-5 transition-colors duration-300"
                    style={{
                      backgroundColor: `${feature.color}10`,
                    }}
                  >
                    <Icon
                      className="w-6 h-6 transition-colors duration-300"
                      style={{ color: feature.color }}
                    />
                  </div>
                  <h3
                    className="text-xl font-bold mb-3"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {feature.title}
                  </h3>
                  <p
                    className="leading-relaxed text-sm"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section
        className="relative z-10 py-20"
        style={{
          backgroundColor: "var(--surface)",
          borderTop: "1px solid var(--border-faint)",
        }}
      >
        <div className="page-container text-center">
          <div
            className="max-w-2xl mx-auto rounded-2xl p-12 animate-pulse-glow"
            style={{
              backgroundColor: "var(--elevated)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <h2
              className="text-2xl md:text-3xl font-bold mb-4"
              style={{ color: "var(--text-primary)" }}
            >
              Ready to get started?
            </h2>
            <p
              className="mb-8"
              style={{ color: "var(--text-secondary)" }}
            >
              Start analyzing companies today with FiftyOne Insights.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => onNavigate("single")}
                className="btn-brand"
              >
                Start Analyzing
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => onNavigate("batch")}
                className="btn-brand-outline"
              >
                Batch Upload
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer
        className="py-8"
        style={{
          borderTop: "1px solid var(--border-faint)",
          backgroundColor: "var(--surface)",
        }}
      >
        <div className="page-container">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <div
                className="w-6 h-6 rounded flex items-center justify-center"
                style={{ backgroundColor: "var(--brand-glow)" }}
              >
                <div
                  className="w-3 h-3 rounded-sm"
                  style={{ backgroundColor: "var(--brand)" }}
                />
              </div>
              <span
                className="font-semibold"
                style={{ color: "var(--text-primary)" }}
              >
                FiftyOne Insights
              </span>
            </div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              © 2026 FiftyOne Insights Platform.
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
