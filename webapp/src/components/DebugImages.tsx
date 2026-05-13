"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { imageSrc } from "@/lib/image";

interface DebugPanel {
  key: string;
  label: string;
  b64?: string;
}

interface Props {
  panels: DebugPanel[];
  gridClassName?: string;
  imageMaxHeight?: number;
}

export default function DebugImages({
  panels,
  gridClassName = "grid grid-cols-2 lg:grid-cols-3 gap-3",
  imageMaxHeight = 200,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div>
      <div className={gridClassName}>
        {panels.map(({ key, label, b64 }) => (
          <Card
            key={key}
            className="overflow-hidden cursor-pointer transition-colors hover:border-primary/40"
            style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}
            onClick={() => setSelected(selected === key ? null : key)}
          >
            <CardHeader className="px-3 py-2 flex-row items-center justify-between">
              <span className="text-xs font-jetbrains" style={{ color: "var(--charm-muted)" }}>
                {label}
              </span>
              {b64 && (
                <span className="text-xs font-jetbrains" style={{ color: "var(--charm-cyan)" }}>
                  ▸ expand
                </span>
              )}
            </CardHeader>
            <CardContent className="p-0">
              {b64 ? (
                <img
                  src={imageSrc(b64)}
                  alt={label}
                  className="w-full object-contain"
                  style={{ maxHeight: imageMaxHeight, background: "var(--background)" }}
                />
              ) : (
                <div
                  className="h-32 flex items-center justify-center text-xs font-jetbrains"
                  style={{ color: "var(--charm-muted)" }}
                >
                  no image
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {selected &&
        (() => {
          const panel = panels.find((p) => p.key === selected);
          if (!panel?.b64) return null;
          return (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm"
              style={{ background: "oklch(0 0 0 / 0.8)" }}
              onClick={() => setSelected(null)}
            >
              <div
                className="max-w-4xl max-h-[90vh] w-full mx-4"
                onClick={(e) => e.stopPropagation()}
              >
                <Card style={{ background: "var(--charm-card)", borderColor: "var(--charm-border)" }}>
                  <CardHeader className="px-4 py-3 flex-row items-center justify-between">
                    <span className="font-jetbrains text-sm" style={{ color: "var(--charm-text)" }}>
                      {panel.label}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelected(null)}
                      style={{ color: "var(--charm-muted)" }}
                    >
                      ✕
                    </Button>
                  </CardHeader>
                  <CardContent className="p-0">
                    <img
                      src={imageSrc(panel.b64)}
                      alt={panel.label}
                      className="w-full object-contain"
                      style={{ maxHeight: "78vh" }}
                    />
                  </CardContent>
                </Card>
              </div>
            </div>
          );
        })()}
    </div>
  );
}
