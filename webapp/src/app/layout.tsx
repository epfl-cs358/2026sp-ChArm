import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import SerialSniffer from "@/components/SerialSniffer";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CalibrationProvider } from "@/lib/calibration-context";

export const metadata: Metadata = {
  title: "ChArm — Vision Dashboard",
  description: "Chess robot CV monitoring & calibration",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="flex min-h-screen bg-background">
        <CalibrationProvider>
          <TooltipProvider delay={120}>
            <Sidebar />
            <main className="flex-1 overflow-auto pb-8">{children}</main>
            <SerialSniffer />
          </TooltipProvider>
        </CalibrationProvider>
      </body>
    </html>
  );
}
