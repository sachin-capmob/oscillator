import type { Metadata } from "next";
import "./globals.css";

import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "Linear Team Activity Dashboard",
  description: "Individual + team activity insights from Linear",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
