import { useEffect, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useChatStore } from "../stores/chatStore";
import { MessageThread } from "../components/chat/MessageThread";
import { ChatInputBar } from "../components/chat/ChatInputBar";
import { AlertCircle, MessageSquareText, X } from "lucide-react";

export default function ChatView() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = (location.state as { prefill?: string } | null)?.prefill;

  const {
    messages,
    conversations,
    activeConversationId,
    isLoading,
    error,
    streamMessage,
    loadConversation,
    setActiveConversation,
    clearError,
  } = useChatStore();

  const conversationTitle =
    conversations.find((c) => c.conversation_id === conversationId)?.title ?? null;

  useEffect(() => {
    if (conversationId && conversationId !== activeConversationId) {
      setActiveConversation(conversationId);
      const existing = messages[conversationId];
      if (!existing?.length) loadConversation(conversationId);
    } else if (!conversationId && activeConversationId) {
      setActiveConversation(null);
    }
  }, [
    activeConversationId,
    conversationId,
    loadConversation,
    messages,
    setActiveConversation,
  ]);

  const currentMessages = conversationId
    ? (messages[conversationId] ?? [])
    : activeConversationId
      ? (messages[activeConversationId] ?? [])
      : [];
  const hasActiveConversation = Boolean(conversationId);

  const handleSend = useCallback(
    async (text: string) => {
      await streamMessage(text, conversationId ?? null, (id) => {
        if (!conversationId) {
          navigate(`/chat/${id}`, { replace: true });
        }
      });
    },
    [conversationId, streamMessage, navigate],
  );

  useEffect(() => {
    if (prefill) {
      handleSend(prefill);
      window.history.replaceState({}, "", window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-(--bg)">
      {hasActiveConversation && (
        <div className="shrink-0 border-b border-(--border) bg-(--bg)">
          <div className="chat-content">
            <div className="flex flex-col gap-3 py-4 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <div className="surface-card flex h-10 w-10 items-center justify-center">
                    <MessageSquareText size={16} style={{ color: "var(--accent)" }} />
                  </div>
                  <div className="min-w-0">
                    <p className="eyebrow mb-1">Analyst workspace</p>
                    <h1 className="heading-section m-0">{conversationTitle ?? "Conversation"}</h1>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="chat-content" style={{ paddingTop: "18px", paddingBottom: 0 }}>
          <div
            className="page-banner flex w-full items-start gap-3 animate-fade-in"
            style={{ borderColor: "var(--risk-high-border)", background: "var(--danger-soft)" }}
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0" style={{ color: "var(--risk-high)" }} />
            <p className="flex-1 text-sm" style={{ color: "var(--text-pri)" }}>
              {error}
            </p>
            <button
              onClick={clearError}
              className="shrink-0 rounded p-1 text-(--text-ter) transition-colors hover:text-(--text-pri)"
            >
              <X size={13} />
            </button>
          </div>
        </div>
      )}

      <MessageThread messages={currentMessages} />

      <ChatInputBar onSend={handleSend} isLoading={isLoading} sticky={hasActiveConversation} />
    </div>
  );
}
