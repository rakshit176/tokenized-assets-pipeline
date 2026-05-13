"use client";

import { useState } from "react";
import Image from "next/image";
import { Menu } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetClose,
} from "@/components/ui/sheet";

type ViewType = "landing" | "single" | "batch" | "results" | "details";

interface HeaderProps {
  currentView: ViewType;
  setCurrentView: (view: ViewType) => void;
}

const appLinks: { id: ViewType; label: string }[] = [
  { id: "landing", label: "Home" },
  { id: "single", label: "Analyze" },
  { id: "batch", label: "Batch" },
  { id: "results", label: "Results" },
];

export default function Header({ currentView, setCurrentView }: HeaderProps) {
  return (
    <nav className="nav-glass sticky top-0 z-50">
      <div
        className="flex items-center justify-between h-16"
        style={{ maxWidth: "var(--page-width)", margin: "0 auto", padding: "0 var(--page-gutter)" }}
      >
        {/* Nav Left */}
        <div className="flex items-center gap-4">
          {/* Logo */}
          <button
            onClick={() => setCurrentView("landing")}
            className="flex items-center gap-2.5 hover:opacity-80 transition-opacity focus-brand rounded"
            style={{ fontFamily: "var(--font-sora)" }}
          >
            <Image
              src="https://fiftyone.xyz/images/logo.png"
              alt="51 Insights"
              width={32}
              height={28}
              className="object-contain"
              unoptimized
            />
            <span
              className="hidden sm:inline"
              style={{
                fontSize: "12px",
                fontWeight: 400,
                color: "var(--text-primary)",
                letterSpacing: "-0.02em",
              }}
            >
              Fiftyone
            </span>
          </button>
        </div>

        {/* Nav Actions */}
        <div className="hidden md:flex items-center gap-3">
          {/* App Navigation Links */}
          <div
            className="flex items-center gap-0.5 p-1 rounded-lg"
            style={{ backgroundColor: "var(--elevated)", border: "1px solid var(--border-faint)" }}
          >
            {appLinks.map((link) => {
              const isActive = currentView === link.id;
              return (
                <button
                  key={link.id}
                  onClick={() => setCurrentView(link.id)}
                  className="px-3 py-1.5 rounded-md text-sm font-medium transition-all"
                  style={{
                    fontFamily: "var(--font-dm-sans)",
                    backgroundColor: isActive ? "var(--brand)" : "transparent",
                    color: isActive ? "#ffffff" : "var(--text-secondary)",
                    boxShadow: isActive ? "0 0 15px var(--brand-glow)" : "none",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = "var(--text-primary)";
                      e.currentTarget.style.backgroundColor = "var(--elevated-2)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = "var(--text-secondary)";
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                  }}
                >
                  {link.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Mobile Menu */}
        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <button
                className="p-2 rounded-md transition-colors"
                style={{ color: "var(--text-secondary)" }}
                aria-label="Menu"
              >
                <Menu width={20} height={20} />
              </button>
            </SheetTrigger>
            <SheetContent
              side="right"
              className="w-[300px] border-none"
              style={{
                backgroundColor: "var(--surface)",
                borderLeft: "1px solid var(--border-subtle)",
              }}
            >
              <div className="flex flex-col gap-6 pt-8">
                {/* App Nav */}
                <div className="flex flex-col gap-1">
                  <p
                    className="px-3 py-1 text-xs font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-faint)" }}
                  >
                    Navigate
                  </p>
                  {appLinks.map((link) => {
                    const isActive = currentView === link.id;
                    return (
                      <SheetClose asChild key={link.id}>
                        <button
                          onClick={() => setCurrentView(link.id)}
                          className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left"
                          style={{
                            backgroundColor: isActive
                              ? "var(--brand)"
                              : "transparent",
                            color: isActive
                              ? "#ffffff"
                              : "var(--text-secondary)",
                          }}
                        >
                          {link.label}
                        </button>
                      </SheetClose>
                    );
                  })}
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </nav>
  );
}
