"use client";

import { useState } from "react";
import Header from "@/components/Header";
import Landing from "@/components/Landing";
import SingleProcess from "@/components/SingleProcess";
import BatchProcess from "@/components/BatchProcess";
import ResultsTable from "@/components/ResultsTable";
import CompanyDetails from "@/components/CompanyDetails";

type ViewType = "landing" | "single" | "batch" | "results" | "details";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [currentView, setCurrentView] = useState<ViewType>("landing");
  const [selectedCompany, setSelectedCompany] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string | undefined>(
    undefined
  );

  const handleViewCompany = (company: Record<string, unknown>) => {
    setSelectedCompany(company);
    setSelectedDomain((company as { domain?: string }).domain);
    setCurrentView("details");
  };

  const handleAnalyzeDomain = (domain: string) => {
    setSelectedDomain(domain);
    setSelectedCompany({ domain, company_name: domain });
    setCurrentView("single");
  };

  const handleBackFromDetails = () => {
    setCurrentView("results");
  };

  const renderView = () => {
    switch (currentView) {
      case "landing":
        return (
          <Landing
            onNavigate={(view) => setCurrentView(view)}
            onAnalyzeDomain={handleAnalyzeDomain}
          />
        );
      case "single":
        return (
          <SingleProcess
            apiUrl={API_URL}
            onViewResults={() => setCurrentView("results")}
            onViewCompany={handleViewCompany}
          />
        );
      case "batch":
        return (
          <BatchProcess
            apiUrl={API_URL}
            onViewResults={() => setCurrentView("results")}
            onViewCompany={handleViewCompany}
          />
        );
      case "results":
        return (
          <ResultsTable
            apiUrl={API_URL}
            onViewCompany={handleViewCompany}
            onNewProcess={() => setCurrentView("single")}
          />
        );
      case "details":
        return (
          <CompanyDetails
            apiUrl={API_URL}
            onBack={handleBackFromDetails}
            companyDomain={selectedDomain}
            companyData={selectedCompany || undefined}
          />
        );
      default:
        return (
          <Landing
            onNavigate={(view) => setCurrentView(view)}
            onAnalyzeDomain={handleAnalyzeDomain}
          />
        );
    }
  };

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "#000000" }}
    >
      <Header currentView={currentView} setCurrentView={setCurrentView} />
      <main className="flex-1">{renderView()}</main>
    </div>
  );
}
