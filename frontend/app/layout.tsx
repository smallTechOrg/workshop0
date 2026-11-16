import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "highlight.js/styles/github.css";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { SITE_URL } from "@/lib/site";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

/**
 * Defaults only: a title, a description and `metadataBase`. Canonical, Open
 * Graph and Twitter tags are set per public page (`lib/site.ts`), never here,
 * so they are not inherited by the listing and trainer templates whose head
 * the server rewrites (api.md §Phase 11e, §Phase 13, §Phase 13b).
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "Workshop0",
  description:
    "Workshop0 by smallTech: the Trainer Network and Opportunity Board for Generative AI, agentic AI and tech trainers, plus a free toolkit for running hands-on workshops.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen font-sans">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
