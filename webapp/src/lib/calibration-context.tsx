"use client";

/**
 * Root-level context holding state shared across the dashboard, robot,
 * and lab pages: vision calibration, robot status, and the live
 * `armCalibrated` flag. Lifting these out of per-page state lets the SPA
 * preserve them across client-side navigations. A hard refresh (F5)
 * naturally resets `armCalibrated` to false, forcing a fresh
 * `arm-calibrate` before the player can move.
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
import type { CalibrationData, RobotStatus } from "@/lib/types";

type CalibrationContextValue = {
  calibration: CalibrationData | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  setCalibration: (next: CalibrationData | null) => void;
  // Physical states shared across pages.
  armCalibrated: boolean;
  setArmCalibrated: (value: boolean) => void;
  robotStatus: RobotStatus | null;
  setRobotStatus: (next: RobotStatus | null) => void;
  refreshRobotStatus: () => Promise<RobotStatus | null>;
};

const CalibrationContext = createContext<CalibrationContextValue | null>(null);

export function CalibrationProvider({ children }: { children: ReactNode }) {
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [armCalibrated, setArmCalibrated] = useState(false);
  const [robotStatus, setRobotStatus] = useState<RobotStatus | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);
  const robotInFlight = useRef<Promise<RobotStatus | null> | null>(null);

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

  const refreshRobotStatus = useCallback(async (): Promise<RobotStatus | null> => {
    if (robotInFlight.current) return robotInFlight.current;
    const p = (async () => {
      try {
        const data = await api.getRobotStatus();
        setRobotStatus(data);
        return data;
      } catch {
        return null;
      } finally {
        robotInFlight.current = null;
      }
    })();
    robotInFlight.current = p;
    return p;
  }, []);

  useEffect(() => {
    void refresh();
    void refreshRobotStatus();
  }, [refresh, refreshRobotStatus]);

  const value = useMemo<CalibrationContextValue>(
    () => ({
      calibration,
      isLoading,
      error,
      refresh,
      setCalibration,
      armCalibrated,
      setArmCalibrated,
      robotStatus,
      setRobotStatus,
      refreshRobotStatus,
    }),
    [calibration, isLoading, error, refresh, armCalibrated, robotStatus, refreshRobotStatus],
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
