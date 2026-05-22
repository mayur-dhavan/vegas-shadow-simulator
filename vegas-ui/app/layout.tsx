import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vegas Shadow Simulator",
  description: "AWS AI League 2026 Global Finals — Tournament Simulator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white min-h-screen font-mono">{children}</body>
    </html>
  );
}
