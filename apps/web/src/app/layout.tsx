import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = { title: "Pagerwise", description: "Incidents and their triage briefs, live" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top"><Link href="/">Pagerwise</Link><span className="muted">incidents, live</span></header>
        <main><Providers>{children}</Providers></main>
      </body>
    </html>
  );
}
