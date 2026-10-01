"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Mode = "user" | "research";
const Ctx = createContext<{ mode: Mode; setMode: (m: Mode) => void }>({ mode: "user", setMode: () => {} });

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>("user");
  useEffect(() => {
    try { const m = localStorage.getItem("docmind.mode"); if (m === "research" || m === "user") setModeState(m); } catch {}
  }, []);
  const setMode = (m: Mode) => { setModeState(m); try { localStorage.setItem("docmind.mode", m); } catch {} };
  return <Ctx.Provider value={{ mode, setMode }}>{children}</Ctx.Provider>;
}
export const useMode = () => useContext(Ctx);
