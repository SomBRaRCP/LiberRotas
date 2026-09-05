import { AppState } from "react-native";
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const API_URL = process.env.EXPO_PUBLIC_TRQ_BEC_API_URL?.trim().replace(/\/+$/, "") || "";
const CLOCK_TICK_MS = 1_000;
const CLOCK_RESYNC_MS = 5 * 60_000;
const CLOCK_REQUEST_TIMEOUT_MS = 5_000;

type ClockStatus = "synchronized" | "syncing" | "offline";

type TrustedClockValue = {
  nowMs: number;
  status: ClockStatus;
  lastSynchronizedAtMs: number | null;
  synchronize: () => Promise<void>;
};

type ServerTimeResponse = {
  server_time_ms?: unknown;
  server_time_iso?: unknown;
  timezone?: unknown;
};

const TrustedClockContext = createContext<TrustedClockValue | null>(null);

/**
 * Mantém um relógio visual atualizado e corrige o desvio do aparelho pela hora
 * do backend. A API continua sendo a autoridade final para expirações e
 * validações; este contexto serve apenas para exibir relógio e contagens.
 */
export function TrustedClockProvider({ children }: PropsWithChildren) {
  const [deviceNowMs, setDeviceNowMs] = useState(() => Date.now());
  const [serverOffsetMs, setServerOffsetMs] = useState(0);
  const [status, setStatus] = useState<ClockStatus>(API_URL ? "syncing" : "offline");
  const [lastSynchronizedAtMs, setLastSynchronizedAtMs] = useState<number | null>(null);
  const requestInProgress = useRef(false);

  const synchronize = useCallback(async () => {
    if (!API_URL || requestInProgress.current) {
      if (!API_URL) setStatus("offline");
      return;
    }

    requestInProgress.current = true;
    setStatus((current) => current === "synchronized" ? current : "syncing");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CLOCK_REQUEST_TIMEOUT_MS);
    const requestStartedAtMs = Date.now();

    try {
      const response = await fetch(`${API_URL}/v1/time`, {
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP_${response.status}`);

      const payload = await response.json() as ServerTimeResponse;
      const requestFinishedAtMs = Date.now();
      if (
        !Number.isSafeInteger(payload.server_time_ms)
        || payload.timezone !== "UTC"
        || typeof payload.server_time_iso !== "string"
      ) {
        throw new Error("SERVER_TIME_RESPONSE_INVALID");
      }

      // O ponto médio reduz o erro introduzido pelo tempo de ida e volta da rede.
      const requestMidpointMs = requestStartedAtMs + (requestFinishedAtMs - requestStartedAtMs) / 2;
      setServerOffsetMs(Number(payload.server_time_ms) - requestMidpointMs);
      setDeviceNowMs(requestFinishedAtMs);
      setLastSynchronizedAtMs(requestFinishedAtMs);
      setStatus("synchronized");
    } catch {
      // Sem conexão, o relógio visual continua no aparelho. A API ainda rejeita
      // qualquer cupom, feira ou prova de segurança fora do prazo no servidor.
      setStatus("offline");
    } finally {
      clearTimeout(timeout);
      requestInProgress.current = false;
    }
  }, []);

  useEffect(() => {
    // Agenda a primeira sincronizacao como trabalho externo do efeito. Alem de
    // evitar uma atualizacao de estado sincrona durante a montagem, isso
    // permite cancelar a chamada caso o provider seja desmontado de imediato.
    const initialSync = setTimeout(() => void synchronize(), 0);
    const tick = setInterval(() => setDeviceNowMs(Date.now()), CLOCK_TICK_MS);
    const resync = setInterval(() => void synchronize(), CLOCK_RESYNC_MS);
    const appState = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active") void synchronize();
    });

    return () => {
      clearTimeout(initialSync);
      clearInterval(tick);
      clearInterval(resync);
      appState.remove();
    };
  }, [synchronize]);

  const value = useMemo<TrustedClockValue>(() => ({
    nowMs: deviceNowMs + serverOffsetMs,
    status,
    lastSynchronizedAtMs,
    synchronize,
  }), [deviceNowMs, lastSynchronizedAtMs, serverOffsetMs, status, synchronize]);

  return <TrustedClockContext.Provider value={value}>{children}</TrustedClockContext.Provider>;
}

export function useTrustedClock() {
  const value = useContext(TrustedClockContext);
  if (!value) throw new Error("useTrustedClock precisa estar dentro de TrustedClockProvider");
  return value;
}
