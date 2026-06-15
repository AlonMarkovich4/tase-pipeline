import type { Metadata } from "next";
import { Heebo } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/AppShell";

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
  return (
    <html lang="he" dir="rtl" className={`${heebo.variable} h-full`}>
      <body className="min-h-full">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
