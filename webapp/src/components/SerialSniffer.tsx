"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, SerialLogEntry } from "@/lib/api";
import { ChevronDown, ChevronUp, Circle, Trash2 } from "lucide-react";

export default function SerialSniffer() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<SerialLogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    if (paused) return;
    try {
      const { entries: fresh } = await api.serialLog(150);
      setEntries(fresh);
    } catch {
      // non-fatal — backend might not be running
    }
  }, [paused]);

  useEffect(() => {
    if (!open) return;
    poll();
    const id = window.setInterval(poll, 1500);
    return () => window.clearInterval(id);
  }, [open, poll]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, open]);

  return (
    <div
      className="fixed bottom-0 left-56 right-0 z-40 border-t font-jetbrains"
      style={{ background: "var(--charm-surface)", borderColor: "var(--charm-border)" }}
    >
      {/* Toggle bar */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-1.5 text-xs"
        style={{ color: "var(--charm-muted)" }}
      >
        <Circle
          className="size-2 shrink-0"
          fill={entries.length > 0 ? "var(--charm-cyan)" : "transparent"}
          style={{ color: entries.length > 0 ? "var(--charm-cyan)" : "var(--charm-muted)" }}
        />
        <span className="font-semibold uppercase tracking-widest text-[10px]" style={{ color: "var(--charm-muted)" }}>
          Serial Monitor
        </span>
        {entries.length > 0 && (
          <span className="text-[10px]" style={{ color: "var(--charm-muted)" }}>
            {entries.length} entries
          </span>
        )}
        <span className="ml-auto">{open ? <ChevronDown className="size-3" /> : <ChevronUp className="size-3" />}</span>
      </button>

      {/* Log panel */}
      {open && (
        <div style={{ borderTop: "1px solid var(--charm-border)" }}>
          <div className="flex items-center gap-3 px-4 py-1.5 border-b" style={{ borderColor: "var(--charm-border)" }}>
            <button
              type="button"
              onClick={() => setPaused((v) => !v)}
              className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border"
              style={{
                borderColor: paused ? "oklch(from var(--charm-amber) l c h / 0.5)" : "var(--charm-border)",
                color: paused ? "var(--charm-amber)" : "var(--charm-muted)",
                background: paused ? "oklch(from var(--charm-amber) l c h / 0.08)" : "transparent",
              }}
            >
              {paused ? "▶ resume" : "⏸ pause"}
            </button>
            <button
              type="button"
              onClick={() => setEntries([])}
              className="flex items-center gap-1 text-[10px] uppercase tracking-wider"
              style={{ color: "var(--charm-muted)" }}
            >
              <Trash2 className="size-3" /> clear
            </button>
            <span className="ml-auto text-[10px]" style={{ color: "var(--charm-muted)" }}>
              TX = sent to Arduino · RX = received
            </span>
          </div>
          <div className="h-40 overflow-auto px-4 py-2 space-y-0.5 text-[11px]">
            {entries.length === 0 ? (
              <p style={{ color: "var(--charm-muted)" }}>No serial activity yet. Send a robot command to see output here.</p>
            ) : (
              entries.map((e, i) => (
                <div key={i} className="flex items-baseline gap-3">
                  <span className="shrink-0 text-[10px]" style={{ color: "var(--charm-muted)", opacity: 0.6 }}>
                    {new Date(e.ts * 1000).toLocaleTimeString()}
                  </span>
                  <span
                    className="shrink-0 w-6 text-[10px] font-semibold uppercase"
                    style={{ color: e.dir === "tx" ? "var(--charm-cyan)" : "var(--charm-amber)" }}
                  >
                    {e.dir}
                  </span>
                  <span style={{ color: "var(--charm-text)", wordBreak: "break-all" }}>{e.text}</span>
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </div>
  );
}
