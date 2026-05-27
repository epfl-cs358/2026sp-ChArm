"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brain, Gauge, LayoutDashboard, SlidersHorizontal, Tags, Waypoints } from "lucide-react";
import { api } from "@/lib/api";
import { Separator } from "@/components/ui/separator";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/lab/labeling", label: "Labeling Wizard", icon: Tags },
  { href: "/lab/cnn", label: "CNN Wizard", icon: Brain },
  { href: "/lab/vision-settings", label: "Vision Settings", icon: SlidersHorizontal },
  { href: "/robot", label: "Scara Calibration", icon: Waypoints },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [status, setStatus] = useState<"ok" | "error" | "loading">("loading");

  useEffect(() => {
    const check = async () => {
      try {
        await api.health();
        setStatus("ok");
      } catch {
        setStatus("error");
      }
    };
    check();
    const t = setInterval(check, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <aside
      className="sticky top-0 h-screen w-56 min-h-screen flex flex-col shrink-0"
      style={{ background: "var(--charm-surface)", borderRight: "1px solid var(--charm-border)" }}
    >
      <div className="px-5 py-6">
        <div className="flex items-start justify-between gap-3 mb-1">
          <div className="flex items-center gap-2">
            <Gauge className="size-5" style={{ color: "var(--charm-cyan)" }} />
            <span
              className="font-jetbrains font-semibold text-sm tracking-widest"
              style={{ color: "var(--charm-text)" }}
            >
              ChArm
            </span>
          </div>
        </div>
        <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
          Vision Dashboard
        </p>
      </div>

      <Separator style={{ background: "var(--charm-border)" }} />

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-jetbrains transition-all"
              style={{
                color: active ? "var(--charm-cyan)" : "var(--charm-muted)",
                background: active ? "oklch(from var(--charm-cyan) l c h / 0.1)" : "transparent",
                border: active ? "1px solid oklch(from var(--charm-cyan) l c h / 0.28)" : "1px solid transparent",
              }}
            >
              <Icon className="size-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      <Separator style={{ background: "var(--charm-border)" }} />

      <div className="px-4 py-4 flex items-center gap-2">
        <span
          className={`status-dot ${
            status === "ok"
              ? "status-ok"
              : status === "error"
                ? "status-error"
                : "status-loading"
          }`}
        />
        <div>
          <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)" }}>
            API {status === "ok" ? "online" : status === "error" ? "offline" : "..."}
          </p>
          <p className="font-jetbrains text-xs" style={{ color: "var(--charm-muted)", opacity: 0.5 }}>
            :8765
          </p>
        </div>
      </div>
    </aside>
  );
}
