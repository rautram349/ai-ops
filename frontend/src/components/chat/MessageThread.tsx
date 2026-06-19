import { useEffect, useRef } from "react";
import { CheckCircle2, Sparkles, XCircle } from "lucide-react";
import type { OptimisticMessage } from "../../types/api";
import { UserMessage } from "./UserMessage";
import { AssistantMessage } from "./AssistantMessage";

interface MessageThreadProps {
  messages: OptimisticMessage[];
}

function EmptyState() {
  return (
    <div className="flex w-full flex-col items-center justify-center px-4 py-6 sm:px-6 xl:px-8">
      <div className="animate-fade-in" style={{ width: "min(100%, 58rem)" }}>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center surface-card-lg shadow-none">
              <Sparkles size={20} style={{ color: "var(--accent)" }} />
            </div>

            <div>
              <p className="eyebrow mb-1.5">Investigation workspace</p>
              <h2 className="heading-page mb-1.5">AI-ops</h2>
              <p
                style={{
                  color: "color-mix(in srgb, var(--text-sec) 85%, var(--text-pri) 15%)",
                  fontSize: "var(--text-base)",
                  maxWidth: "31rem",
                  lineHeight: 1.6,
                  margin: "0 auto",
                }}
              >
                Ask for root-cause analysis, operational summaries, or recommended actions across revenue,
                stock, campaigns, and support.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MessageThread({ messages }: MessageThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (!messages.length) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div
          className="chat-content"
          style={{
            minHeight: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            paddingTop: "20px",
            paddingBottom: "12px",
          }}
        >
          <EmptyState />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain scroll-smooth">
      <div className="chat-content" style={{ paddingTop: "32px", paddingBottom: "32px", minHeight: "100%" }}>
        <div className="flex min-h-full flex-col gap-6">
          {messages.map((m) => {
            if (m.isSystemEvent) {
              const isSuccess = m.content.startsWith("✓");
              return (
                <div key={m.message_id} className="flex justify-center animate-fade-in">
                  <div
                    className="event-chip"
                    style={{
                      background: isSuccess ? "var(--success-soft)" : "var(--danger-soft)",
                      border: isSuccess
                        ? "1px solid var(--success-border)"
                        : "1px solid var(--danger-border)",
                    }}
                  >
                    {isSuccess ? (
                      <CheckCircle2 size={14} style={{ color: "var(--risk-low)", flexShrink: 0 }} />
                    ) : (
                      <XCircle size={14} style={{ color: "var(--risk-high)", flexShrink: 0 }} />
                    )}
                    <span>{m.content}</span>
                  </div>
                </div>
              );
            }

            return m.role === "user" ? (
              <UserMessage key={m.message_id} message={m} />
            ) : (
              <AssistantMessage key={m.message_id} message={m} />
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
