import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import Header from "@/components/Header";
import { ModeProvider } from "@/components/ModeContext";

export const metadata: Metadata = { title: "DocMind", description: "Ask a document a question two ways and see where the answers differ." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ModeProvider>
          <div className="flex h-screen flex-col">
            <Header />
            <div className="min-h-0 flex-1">{children}</div>
          </div>
        </ModeProvider>
      </body>
    </html>
  );
}
