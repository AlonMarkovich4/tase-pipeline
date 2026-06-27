import type { Metadata } from "next";
import { after } from "next/server";
import { Heebo } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/AppShell";
import { settleDueDemoTrades } from "@/app/demo/actions";

const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  variable: "--font-heebo",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "GMM — TLV35",
  description: "TLV35 options trading dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Settle expired demo trades on EVERY dashboard load (any page), reducing the
  // visit-dependence of the demo-page-only trigger. Runs via next/server `after`,
  // i.e. AFTER the response is sent — it never blocks or delays rendering, and a
  // slow/failed sweep can't hold up the page. The sweep is atomic + idempotent
  // (425a893), so firing it on every page is safe (no double-count). Errors are
  // swallowed inside the action and re-guarded here, so a sweep failure never
  // breaks a page. Skip the production-build phase (where `after` would otherwise
  // run at build) so the sweep only fires on real requests.
  if (process.env.NEXT_PHASE !== "phase-production-build") {
    after(async () => {
      try {
        await settleDueDemoTrades();
      } catch {
        /* never let a settlement sweep break a dashboard page */
      }
    });
  }
  return (
    <html lang="he" dir="rtl" className={`${heebo.variable} h-full`}>
      <body className="min-h-full">
        <script
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light')}catch(e){}`,
          }}
        />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
