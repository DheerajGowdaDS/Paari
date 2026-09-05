"use client";

import { useCallback, useRef, useState } from "react";
import {
  getStoredToken,
  storeToken,
  clearToken,
  postAgentToken,
  postAutorunAbort,
  type AutorunEvent,
} from "@/lib/buyerApi";

async function fetchFreshToken(): Promise<string> {
  const data = await postAgentToken({ agent_type: "buyer", agent_id: "BA-001" });
  const token = data.access_token;
  if (token) storeToken(token);
  return token;
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  let token = getStoredToken();
  if (!token) token = await fetchFreshToken();
  const makeRequest = (t: string) =>
    fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}`, ...init?.headers },
    });
  let res = await makeRequest(token);
  if (res.status === 401) {
    clearToken();
    token = await fetchFreshToken();
    res = await makeRequest(token);
  }
  return res;
}

interface UseAutorunOptions {
  sessionId: string;
  onEvent: (event: AutorunEvent) => void;
  onDone: (txnId: string, quoteId: string, decision: AutorunEvent["decision"]) => void;
  onAbort: () => void;
  onError: (message: string) => void;
}

type AutorunStatus = "idle" | "running" | "done" | "aborted";

export function useAutorun({
  sessionId,
  onEvent,
  onDone,
  onAbort,
  onError,
}: UseAutorunOptions) {
  const [status, setStatus] = useState<AutorunStatus>("idle");
  const [currentSeq, setCurrentSeq] = useState(0);
  const [currentText, setCurrentText] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeSessionRef = useRef<string | null>(null);
  const abortFiredRef = useRef(false);

  const run = useCallback(
    async (scenario = "snowboard-bundle-01") => {
      let token = getStoredToken();
      if (!token) {
        const data = await postAgentToken({ agent_type: "buyer", agent_id: "BA-001" });
        token = data.access_token;
        storeToken(token);
      }

      const ctrl = new AbortController();
      abortControllerRef.current = ctrl;
      activeSessionRef.current = sessionId;
      abortFiredRef.current = false;
      setStatus("running");
      setCurrentSeq(0);
      setCurrentText("");

      try {
        const res = await authFetch("/api/agent/buyer/autorun", {
          method: "POST",
          signal: ctrl.signal,
          body: JSON.stringify({ scenario, session_id: sessionId }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();

          if (done || ctrl.signal.aborted) {
            if (!ctrl.signal.aborted) {
              setStatus("done");
            }
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            if (!raw) continue;

            try {
              const event: AutorunEvent = JSON.parse(raw);

              if (event.type === "aborted") {
                setStatus("aborted");
                onAbort();
                onEvent(event);
                return;
              }

              onEvent(event);
              if (event.seq) setCurrentSeq(event.seq);
              if (event.text) setCurrentText(event.text);

              if (event.type === "done") {
                setStatus("done");
                const txnId = event.txn_id ?? "";
                const quoteId = event.quote_id ?? "";
                onDone(txnId, quoteId, event.decision);
                return;
              }
            } catch {
              // skip malformed lines
            }
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          setStatus("aborted");
          if (!abortFiredRef.current) {
            abortFiredRef.current = true;
            onAbort();
          }
        } else {
          const msg = err instanceof Error ? err.message : "Autorun failed";
          setStatus("idle");
          onError(msg);
        }
      }
    },
    [sessionId, onEvent, onDone, onAbort, onError]
  );

  const runScenario = useCallback(
    (scenario: string) => {
      void run(scenario);
    },
    [run]
  );

  const abort = useCallback(async () => {
    abortFiredRef.current = true;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }      const sid = activeSessionRef.current ?? sessionId;
      try {
        await authFetch("/api/agent/buyer/autorun/abort", {
          method: "POST",
          body: JSON.stringify({ session_id: sid }),
        });
      } catch {
        // abort is idempotent, ignore errors
      }
  }, [sessionId]);

  return { status, currentSeq, currentText, run, runScenario, abort };
}
