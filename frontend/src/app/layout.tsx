import type { Metadata } from "next";
import { Sora, DM_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "FiftyOne Insights - Intelligence Platform",
  description:
    "Advanced data gathering, deep profiling, and real-time intelligence for companies. Precision analytics wrapped in a stunning experience.",
  keywords: [
    "FiftyOne",
    "Insights",
    "Intelligence",
    "Analytics",
    "Data Profiling",
  ],
  authors: [{ name: "FiftyOne" }],
  icons: {
    icon: "https://fiftyone.xyz/images/logo.png",
  },
  openGraph: {
    title: "FiftyOne Insights",
    description: "Intelligence at Scale",
    siteName: "FiftyOne",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${sora.variable} ${dmSans.variable} ${ibmPlexMono.variable} antialiased`}
        style={{ backgroundColor: "#000000", color: "#ededed" }}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
