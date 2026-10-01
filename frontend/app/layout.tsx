import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "./globals.css";
import Footer from "@/components/Footer";
import Header from "@/components/Header";
import { ModeProvider } from "@/components/ModeContext";

export const metadata: Metadata = { title: "DocMind", description: "Ask a document a question two ways and see where the answers differ." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Apply the saved (or system) theme before the first paint, so dark mode never flashes light. */}
        <script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('docmind.theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}" }} />
      </head>
      <body>
        <ModeProvider>
          <div className="flex h-screen flex-col">
            <Header />
            <div className="min-h-0 flex-1">{children}</div>
            <Footer />
          </div>
        </ModeProvider>
      </body>
    </html>
  );
}
