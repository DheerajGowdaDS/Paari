"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  getStoredToken,
  storeToken,
  postAgentToken,
  postBuyerChat,
  postEscrowAuthorize,
  getTerms,
  type BuyerChatResponse,
  type EscrowAuthorizeResponse,
  type TermsResponse,
  type AutorunEvent,
} from "@/lib/buyerApi";
import { useAutorun } from "@/lib/useAutorun";
import { AutorunButton } from "@/components/buyer/AutorunButton";
import { AutorunStatusBar } from "@/components/buyer/AutorunStatusBar";
import { AutorunBubble } from "@/components/buyer/AutorunBubble";
import { formatTimeIST } from "@/lib/utils";
import { AutorunDoneCard } from "@/components/buyer/AutorunDoneCard";

const LOGO_URL =
  "https://lh3.googleusercontent.com/aida/AEtjO1V1hMa6JlEw507615UgeX6HLIGHdLGAVwZtuEzaqYF_CY7OF5iKop9RDLiWgJF2CsASwHY9lZ6sly3zk7Hxo6jBi_Ai6raCwOq2gwCye_pu5wNEb-ZBJ7exThiWBhv7nyViBZfM4DLc5lLHkctS8hNMfivZhmfyAMHPj2C5hLT9hLbgOfu4vDs66nilRUnzP3Edjl1u-WpA1hQrQWMbudRBEw0koISKTuRXFHkBmUqxU-Qml04g1RBMhZLZkhqYJFLzUikvPdwA_Q";

interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  timestamp: Date;
  reply?: BuyerChatResponse["reply"];
  suggestions?: BuyerChatResponse["suggestions"];
  actions?: BuyerChatResponse["actions"];
}

function generateSessionId(): string {
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export default function BuyerPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId] = useState(() => generateSessionId());
  const [notification, setNotification] = useState<{
    visible: boolean;
    message: string;
    type: "success" | "info" | "error";
  }>({ visible: false, message: "", type: "success" });
  const [termsModal, setTermsModal] = useState<TermsResponse | null>(null);
  const [autorunEvents, setAutorunEvents] = useState<AutorunEvent[]>([]);
  const [autorunDone, setAutorunDone] = useState<{
    txnId: string;
    quoteId: string;
    text: string;
    decision?: "ALLOW" | "REVIEW" | "DENY" | "FAILED";
  } | null>(null);
  const notificationRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const humanSentRef = useRef(false);

  const { status: autorunStatus, currentSeq, currentText, run: runAutorun, abort: abortAutorun } = useAutorun({
    sessionId,
    onEvent: (event) => {
      setAutorunEvents((prev) => [...prev, event]);
    },
    onDone: (txnId, quoteId, decision) => {
      setAutorunEvents((prev) => {
        const lastEvent = [...prev].reverse().find((e) => e.type === "done");
        setAutorunDone({
          txnId,
          quoteId,
          text: lastEvent?.text ?? "Bundle ready.",
          decision,
        });
        return prev;
      });
    },
    onAbort: () => {
      showNotification("Autonomous run stopped — you're back in control", "info");
    },
    onError: (message) => {
      showNotification(message, "error");
    },
  });

  useEffect(() => {
    async function initAuth() {
      try {
        const existingToken = getStoredToken();
        console.log("[buyerPage] initAuth - existingToken:", !!existingToken);
        if (!existingToken) {
          console.log("[buyerPage] initAuth - fetching new token...");
          const tokenData = await postAgentToken({
            agent_type: "buyer",
            agent_id: "BA-001",
          });
          console.log("[buyerPage] initAuth - got token, storing...");
          storeToken(tokenData.access_token);
          console.log("[buyerPage] initAuth - token stored successfully");
          setIsAuthenticated(true);
        } else {
          console.log("[buyerPage] initAuth - using existing token");
          setIsAuthenticated(true);
        }
        setAuthError(null);
      } catch (err) {
        console.error("[buyerPage] initAuth - ERROR:", err);
        setAuthError("Failed to authenticate. Please refresh.");
        setIsAuthenticated(false);
      } finally {
        console.log("[buyerPage] initAuth - done, isLoading=false");
        setIsLoading(false);
      }
    }
    initAuth();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const showNotification = useCallback(
    (message: string, type: "success" | "info" | "error" = "success") => {
      setNotification({ visible: true, message, type });
      setTimeout(() => {
        setNotification((prev) => ({ ...prev, visible: false }));
      }, 5000);
    },
    []
  );

  const handleSend = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || isSending || !isAuthenticated) return;

    const userMessage = input.trim();
    setInput("");
    setIsSending(true);

    if (autorunStatus === "running") {
      humanSentRef.current = true;
      await abortAutorun();
    }

    const userMsg: Message = {
      id: generateMessageId(),
      role: "user",
      text: userMessage,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response: BuyerChatResponse = await postBuyerChat({
        session_id: sessionId,
        message: userMessage,
        context: { agent_id: "BA-001" },
      });

      const agentMsg: Message = {
        id: generateMessageId(),
        role: "agent",
        text: response.reply.text,
        timestamp: new Date(),
        reply: response.reply,
        suggestions: response.suggestions,
        actions: response.actions,
      };
      setMessages((prev) => [...prev, agentMsg]);

      if (response.reply.decision === "REVIEW" || response.reply.decision === "DENY") {
        if (response.reply.decision_note) {
          showNotification(response.reply.decision_note, "info");
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Request failed";
      showNotification(errorMessage, "error");
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  const handleSuggestion = (prompt: string) => {
    setInput(prompt);
    inputRef.current?.focus();
  };

  const handleEscrowAuthorize = async () => {
    const lastAgentMsg = [...messages].reverse().find((m) => m.role === "agent" && m.reply?.quote);
    if (!lastAgentMsg?.reply?.quote) return;
    try {
      const response: EscrowAuthorizeResponse = await postEscrowAuthorize({
        quote_id: lastAgentMsg.reply.quote.quote_id,
      });
      showNotification(response.message, "success");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Escrow failed";
      showNotification(errorMessage, "error");
    }
  };

  const handleViewTerms = async () => {
    try {
      const terms: TermsResponse = await getTerms();
      setTermsModal(terms);
    } catch {
      showNotification("Failed to load terms", "error");
    }
  };

  if (isLoading) {
    return (
      <div className="w-full min-h-screen bg-surface flex items-center justify-center">
        <div className="flex flex-col items-center gap-space-md">
          <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
          <span className="font-mono-label text-mono-label text-secondary">Authenticating...</span>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="w-full min-h-screen bg-surface flex items-center justify-center">
        <div className="flex flex-col items-center gap-space-md text-center max-w-md">
          <span className="material-symbols-outlined text-error text-4xl">error</span>
          <p className="font-body-lg text-body-lg text-on-surface">{authError}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-space-lg py-space-sm bg-primary text-on-primary rounded-full font-body-md text-body-md"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-surface text-on-surface font-body-md text-body-md antialiased">
      <header className="fixed top-0 inset-x-0 z-50 bg-surface/85 backdrop-blur-xl border-b border-surface-container-high">
        <div className="h-16 max-w-max-width mx-auto px-gutter-mobile lg:px-gutter-desktop flex items-center justify-between gap-space-md">
          <div className="flex items-center gap-space-md">
            <Link href="/">
              <img
                alt="Paari Logo"
                className="rounded-full object-cover border border-surface-container-high shadow-sm shrink-0"
                style={{ width: 34, height: 34 }}
                src={LOGO_URL}
              />
            </Link>
            <Link
              href="/"
              className="font-headline-sm text-headline-sm text-on-surface tracking-tight font-semibold whitespace-nowrap"
            >
              Paari
            </Link>
            <span className="text-outline-variant">/</span>
            <div className="inline-flex items-center gap-space-xs bg-surface-container-low px-space-sm py-space-2xs rounded-full border border-surface-container-high">
              <span className="font-mono-label text-mono-label uppercase text-on-surface-variant tracking-wider">
                Buyer AI
              </span>
              <span className="text-outline-variant">•</span>
              <span className="font-mono-label text-mono-label text-secondary">
                Console
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-space-lg">
            <Link
              href="/"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Home
            </Link>
            <Link
              href="/merchant"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Merchant
            </Link>
            <Link
              href="/audit"
              className="font-mono-label text-mono-label text-secondary hover:text-on-surface transition-colors tracking-wider"
            >
              Audit
            </Link>
          </nav>
        </div>
      </header>

      <main className="w-full pt-16 min-h-screen bg-surface">
        <div className="flex flex-col w-full min-w-0">
          <div className="w-full max-w-max-width mx-auto px-gutter-mobile lg:px-gutter-desktop py-space-xl lg:py-space-2xl">
            <div className="max-w-[760px] mx-auto flex flex-col gap-space-xl">
              {messages.filter((m) => m.role === "user").length === 0 && autorunStatus !== "running" && (
                <section className="max-w-[760px] mx-auto text-center mb-space-2xl">
                  <div className="flex flex-col items-center gap-space-md">
                    <span className="material-symbols-outlined text-5xl text-secondary">smart_toy</span>
                    <h1 className="font-headline-lg text-headline-lg text-on-surface">
                      {autorunStatus === "done" ? "Run another scenario" : "Welcome to Buyer AI"}
                    </h1>
                    <p className="font-body-lg text-body-lg text-secondary max-w-md">
                      Describe what you need and I will find verified products from merchants. All transactions are governed by Paari for your protection.
                    </p>
                    <AutorunButton
                      onClick={() => runAutorun()}
                      disabled={!isAuthenticated || isSending}
                    />
                    <div className="flex flex-wrap items-center justify-center gap-space-xs">
                      <button
                        className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-300 hover:bg-emerald-100 active:scale-[0.98] transition-all font-body-sm text-body-sm font-medium px-4 py-2 rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
                        type="button"
                        disabled={!isAuthenticated || isSending}
                        onClick={() => runAutorun("snowboard-bundle-01")}
                      >
                        <span className="material-symbols-outlined text-sm leading-none">check_circle</span>
                        PASS · Happy path (ALLOW)
                      </button>
                      <button
                        className="inline-flex items-center gap-1.5 bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 active:scale-[0.98] transition-all font-body-sm text-body-sm font-medium px-4 py-2 rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
                        type="button"
                        disabled={!isAuthenticated || isSending}
                        onClick={() => runAutorun("deny-over-limit")}
                      >
                        <span className="material-symbols-outlined text-sm leading-none">block</span>
                        FAIL · Over ₹5,000 limit (DENY)
                      </button>
                      <button
                        className="inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 active:scale-[0.98] transition-all font-body-sm text-body-sm font-medium px-4 py-2 rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
                        type="button"
                        disabled={!isAuthenticated || isSending}
                        onClick={() => runAutorun("payment-declined")}
                      >
                        <span className="material-symbols-outlined text-sm leading-none">credit_card_off</span>
                        FAIL · Payment declined (graceful)
                      </button>
                    </div>
                  </div>
                </section>
              )}

              {autorunStatus === "running" && (
                <AutorunStatusBar
                  currentSeq={currentSeq}
                  maxSeq={6}
                  currentText={currentText}
                  type={autorunEvents[autorunEvents.length - 1]?.type ?? "llm"}
                  onAbort={abortAutorun}
                />
              )}

              <div className="flex flex-col gap-space-md">
                {messages.map((msg) => (
                  <div key={msg.id}>
                    {msg.role === "user" ? (
                      <div className="flex flex-col items-end gap-space-xs pl-space-xl w-full">
                        <div className="flex items-center gap-space-xs text-secondary font-mono-label text-mono-label mb-space-2xs">
                          <span className="font-medium text-on-surface-variant">Sovereign Principal</span>
                          <span className="">•</span>
                          <span className="">{formatTimeIST(msg.timestamp)}</span>
                        </div>
                        <div className="relative bg-surface-container-low text-on-surface rounded-3xl rounded-tr-sm px-space-lg py-space-md shadow-sm max-w-2xl border border-surface-container-high">
                          <p className="font-body-lg text-body-lg leading-relaxed text-on-surface">{msg.text}</p>
                          <svg className="absolute -right-2.5 top-0 w-4 h-4 text-surface-container-low fill-current pointer-events-none overflow-visible" viewBox="0 0 16 16">
                            <path d="M0,0 C6,1 14,3 16,0 C14,8 8,14 0,16 Z"></path>
                          </svg>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-space-md pr-space-md">
                        <div className="flex items-center gap-space-sm">
                          <div className="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center text-primary shadow-sm">
                            <span className="material-symbols-outlined text-base">psychology</span>
                          </div>
                          <span className="font-headline-sm text-body-lg font-semibold text-on-surface">Buyer AI Agent</span>
                        </div>

                        <div className="relative bg-surface-container rounded-3xl rounded-tl-sm p-space-lg shadow-sm border border-surface-container-high">
                          <svg className="absolute -left-2.5 top-0 w-4 h-4 text-surface-container fill-current pointer-events-none overflow-visible" viewBox="0 0 16 16">
                            <path d="M16,0 C10,1 2,3 0,0 C2,8 8,14 16,16 Z"></path>
                          </svg>

                          <p className="font-body-lg text-body-lg leading-relaxed text-on-surface mb-space-md">{msg.text}</p>

                          {msg.reply?.order && (
                            <div className="flex items-center gap-space-xs mb-space-md">
                              <span className="material-symbols-outlined text-emerald-600 text-lg">check_circle</span>
                              <span className="font-body-md text-body-md font-semibold text-emerald-700">{msg.reply.order.order_label}</span>
                            </div>
                          )}

                          {msg.reply?.decision === "ALLOW" && msg.actions?.includes("inspect_terms") && (
                            <div className="flex flex-wrap items-center gap-space-sm pt-space-xs">
                              {msg.reply.quote && (
                                <button
                                  className="bg-primary text-on-primary font-body-md text-body-md font-medium px-space-lg py-space-sm rounded-full hover:opacity-90 active:scale-[0.98] transition-all shadow-sm flex items-center gap-space-xs whitespace-nowrap"
                                  type="button"
                                  onClick={handleEscrowAuthorize}
                                >
                                  <span className="material-symbols-outlined text-lg leading-none">lock</span>
                                  <span className="">Proceed to Checkout</span>
                                </button>
                              )}
                              <button
                                className="bg-surface-container-low text-on-surface font-body-md text-body-md font-medium px-space-md py-space-sm rounded-full hover:bg-surface-container-highest active:scale-[0.98] transition-all flex items-center gap-space-xs shadow-sm border border-surface-container-high whitespace-nowrap"
                                type="button"
                                onClick={handleViewTerms}
                              >
                                <span className="material-symbols-outlined text-lg leading-none text-secondary">description</span>
                                <span className="">View Full Terms</span>
                              </button>
                            </div>
                          )}

                          {msg.reply?.decision === "REVIEW" && (
                            <div className="flex flex-wrap items-center gap-space-sm pt-space-xs">
                              <button
                                className="bg-surface-container-low text-on-surface font-body-md text-body-md font-medium px-space-md py-space-sm rounded-full hover:bg-surface-container-highest active:scale-[0.98] transition-all flex items-center gap-space-xs shadow-sm border border-surface-container-high whitespace-nowrap"
                                type="button"
                                onClick={handleViewTerms}
                              >
                                <span className="material-symbols-outlined text-lg leading-none text-secondary">description</span>
                                <span className="">View Full Terms</span>
                              </button>
                            </div>
                          )}
                        </div>

                        {msg.suggestions && msg.suggestions.length > 0 && (
                          <div className="flex flex-col gap-space-xs pt-space-sm">
                            <span className="font-mono-label text-mono-label text-secondary uppercase tracking-wider mb-space-3xs">Suggested Inquiries</span>
                            <div className="flex flex-wrap items-center gap-space-xs">
                              {msg.suggestions.map((suggestion, idx) => (
                                <button
                                  key={idx}
                                  className="bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high px-space-md py-space-xs rounded-full font-body-sm text-body-sm shadow-sm transition-all flex items-center gap-1.5 text-left border border-surface-container-high"
                                  type="button"
                                  onClick={() => handleSuggestion(suggestion.prompt)}
                                >
                                  <span className="material-symbols-outlined text-sm text-secondary leading-none">
                                    {idx === 0 ? "description" : idx === 1 ? "sync_problem" : "tune"}
                                  </span>
                                  <span className="">{suggestion.label}</span>
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {autorunEvents.map((event, idx) => (
                  <AutorunBubble
                    key={`auto-${idx}`}
                    event={event}
                    isStreaming={autorunStatus === "running" && idx === autorunEvents.length - 1}
                  />
                ))}

                {autorunDone && (
                  <AutorunDoneCard
                    txnId={autorunDone.txnId}
                    quoteId={autorunDone.quoteId}
                    text={autorunDone.text}
                    decision={autorunDone.decision}
                  />
                )}
              </div>

              {notification.visible && (
                <div
                  className={`rounded-xl p-space-md shadow-md flex items-center justify-between ${
                    notification.type === "error"
                      ? "bg-error-container border border-error/20"
                      : notification.type === "info"
                      ? "bg-secondary-container border border-secondary/20"
                      : "bg-surface-container-lowest border border-emerald-200"
                  }`}
                  ref={notificationRef}
                >
                  <div className="flex items-center gap-space-sm">
                    <span
                      className={`material-symbols-outlined ${
                        notification.type === "error"
                          ? "text-error"
                          : notification.type === "info"
                          ? "text-secondary"
                          : "text-emerald-600"
                      }`}
                    >
                      {notification.type === "error"
                        ? "error"
                        : notification.type === "info"
                        ? "info"
                        : "check_circle"}
                    </span>
                    <div>
                      <p className="font-body-md text-body-md font-semibold text-on-surface">
                        {notification.type === "error"
                          ? "Something went wrong"
                          : notification.type === "info"
                          ? "Notice"
                          : "Success"}
                      </p>
                      <p className="font-body-sm text-body-sm text-secondary">
                        {notification.message}
                      </p>
                    </div>
                  </div>
                  <button
                    className="text-secondary hover:text-on-surface"
                    type="button"
                    onClick={() => setNotification((prev) => ({ ...prev, visible: false }))}
                  >
                    <span className="material-symbols-outlined text-sm">close</span>
                  </button>
                </div>
              )}

              <div className="h-32 w-full"></div>
            </div>
          </div>

          <div className="fixed bottom-0 inset-x-0 z-40 pb-space-lg px-gutter-mobile pointer-events-none">
            <div className="max-w-[760px] mx-auto w-full pointer-events-auto">
              <div className="bg-surface/90 backdrop-blur-xl rounded-2xl shadow-xl p-space-2xs transition-all duration-200 focus-within:shadow-2xl focus-within:bg-surface border border-surface-container-high">
                <form
                  className="flex items-center gap-space-xs px-space-xs py-space-2xs"
                  onSubmit={handleSend}
                >
                  <button
                    className="w-9 h-9 rounded-full flex items-center justify-center text-secondary hover:text-on-surface hover:bg-surface-container-low transition-colors shrink-0"
                    title="Filter verified merchants & policies"
                    type="button"
                  >
                    <span className="material-symbols-outlined text-lg leading-none">
                      tune
                    </span>
                  </button>
                  <input
                    autoComplete="off"
                    className="w-full bg-transparent px-space-xs py-space-xs text-on-surface placeholder:text-outline font-body-md text-body-md focus:outline-none"
                    id="prompt-input"
                    placeholder="Message Buyer AI or instruct a new procurement intent..."
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    ref={inputRef}
                    disabled={isSending}
                  />
                  <div className="flex items-center gap-space-2xs shrink-0">
                    <button
                      className="w-9 h-9 rounded-full flex items-center justify-center text-secondary hover:text-on-surface hover:bg-surface-container-low transition-colors"
                      title="Attach verified proof document"
                      type="button"
                    >
                      <span className="material-symbols-outlined text-lg leading-none">
                        attach_file
                      </span>
                    </button>
                    <button
                      className="w-9 h-9 rounded-full bg-primary text-on-primary flex items-center justify-center hover:opacity-90 active:scale-95 transition-all shadow-sm disabled:opacity-50"
                      id="submit-btn"
                      title="Transmit Sovereign Directive"
                      type="submit"
                      disabled={isSending || !input.trim() || !isAuthenticated}
                    >
                      <span className="material-symbols-outlined text-lg leading-none">
                        {isSending ? "hourglass_empty" : "arrow_upward"}
                      </span>
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </main>

      {termsModal && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-space-md"
          onClick={() => setTermsModal(null)}
        >
          <div
            className="bg-surface-container-lowest rounded-2xl max-w-lg w-full max-h-[80vh] overflow-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-surface-container-lowest border-b border-surface-container-high p-space-lg flex items-center justify-between">
              <h2 className="font-headline-sm text-headline-sm text-on-surface">
                {termsModal.title}
              </h2>
              <button
                onClick={() => setTermsModal(null)}
                className="w-8 h-8 rounded-full flex items-center justify-center text-secondary hover:text-on-surface hover:bg-surface-container-low transition-colors"
              >
                <span className="material-symbols-outlined text-lg">close</span>
              </button>
            </div>
            <div className="p-space-lg">
              <p className="font-body-md text-body-md text-on-surface leading-relaxed">
                {termsModal.body}
              </p>
            </div>
          </div>
        </div>
      )}

      <footer className="w-full border-t border-surface-container-high bg-surface"></footer>
      <div ref={messagesEndRef} />
    </div>
  );
}
