"use client";

/**
 * Calibration context: holds the vision calibration (board + inner warp) at
 * the layout level so navigating between /, /lab, /robot does not refetch
 * or briefly render "no calibration" while the page remounts.
 *
 * Backend remains the source of truth — on hard refresh the provider does
 * one fetch and then caches in React state. Consumers can call refresh()
 * after a write to broadcast the new value to every listener.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { CalibrationData } from "@/lib/types";

type CalibrationContextValue = {
  calibration: CalibrationData | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  setCalibration: (next: CalibrationData | null) => void;
};

const CalibrationContext = createContext<CalibrationContextValue | null>(null);

export function CalibrationProvider({ children }: { children: ReactNode }) {
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);

  const refresh = useCallback(async () => {
    if (inFlight.current) return inFlight.current;
    const p = (async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.getCalibration();
        setCalibration(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load calibration");
      } finally {
        setIsLoading(false);
        inFlight.current = null;
      }
    })();
    inFlight.current = p;
    return p;
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<CalibrationContextValue>(
    () => ({ calibration, isLoading, error, refresh, setCalibration }),
    [calibration, isLoading, error, refresh],
  );

  return (
    <CalibrationContext.Provider value={value}>
      {children}
    </CalibrationContext.Provider>
  );
}

export function useCalibration(): CalibrationContextValue {
  const ctx = useContext(CalibrationContext);
  if (ctx === null) {
    throw new Error(
      "useCalibration must be used inside <CalibrationProvider> (mounted in app/layout.tsx)",
    );
  }
  return ctx;
}
