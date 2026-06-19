import { create } from "zustand";
import * as chatApi from "../api/chat";
import type { ConversationSummary, OptimisticMessage } from "../types/api";

interface ChatState {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  messages: Record<string, OptimisticMessage[]>;
  isLoading: boolean;
  error: string | null;

  sendMessage(
    message: string,
    conversationId: string | null,
  ): Promise<string | null>;
  streamMessage(
    message: string,
    conversationId: string | null,
    onConversationId?: (id: string) => void,
  ): Promise<string | null>;
  injectSystemMessage(conversationId: string, content: string): void;
  loadConversation(id: string): Promise<void>;
  loadConversationList(): Promise<void>;
  archiveConversation(id: string): Promise<void>;
  renameConversation(id: string, title: string): Promise<void>;
  setActiveConversation(id: string | null): void;
  clearError(): void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: {},
  isLoading: false,
  error: null,

  setActiveConversation: (id) => set({ activeConversationId: id }),
  clearError: () => set({ error: null }),

  loadConversationList: async () => {
    try {
      const data = await chatApi.getConversations();
      set({ conversations: data.conversations });
    } catch {
      // silent — sidebar just stays empty
    }
  },

  loadConversation: async (id) => {
    try {
      const data = await chatApi.getConversation(id);
      const msgs: OptimisticMessage[] = data.messages.map((m) => ({
        ...m,
        isOptimistic: false,
        isLoading: false,
      }));
      set((s) => ({
        messages: { ...s.messages, [id]: msgs },
        activeConversationId: id,
      }));
    } catch {
      set({ error: "Failed to load conversation." });
    }
  },

  sendMessage: async (message, conversationId) => {
    const tempId = `optimistic-${Date.now()}`;
    const userMsg: OptimisticMessage = {
      message_id: tempId,
      role: "user",
      content: message,
      structured_response: null,
      created_at: new Date().toISOString(),
      isOptimistic: true,
      isLoading: false,
    };
    const loadingMsg: OptimisticMessage = {
      message_id: `loading-${Date.now()}`,
      role: "assistant",
      content: "",
      structured_response: null,
      created_at: new Date().toISOString(),
      isOptimistic: true,
      isLoading: true,
    };

    const cid = conversationId ?? "new";

    set((s) => ({
      isLoading: true,
      error: null,
      messages: {
        ...s.messages,
        [cid]: [...(s.messages[cid] ?? []), userMsg, loadingMsg],
      },
    }));

    try {
      const res = await chatApi.sendMessage({
        message,
        conversation_id: conversationId,
      });

      const assistantMsg: OptimisticMessage = {
        message_id: res.message_id,
        role: "assistant",
        content: res.response.summary,
        structured_response: res.response,
        created_at: new Date().toISOString(),
        intent: res.intent,
        isOptimistic: false,
        isLoading: false,
      };

      const existingMsgs = get().messages[cid] ?? [];
      const filteredMsgs = existingMsgs.filter((m) => !m.isLoading);

      // Replace the optimistic user message with the real one
      const finalMsgs = filteredMsgs.map((m) =>
        m.message_id === tempId ? { ...m, isOptimistic: false } : m,
      );
      finalMsgs.push(assistantMsg);

      set((s) => {
        const updated = { ...s.messages };
        delete updated[cid];
        updated[res.conversation_id] = finalMsgs;

        // Update conversation list
        const existing = s.conversations.find(
          (c) => c.conversation_id === res.conversation_id,
        );
        const updatedConvos = existing
          ? s.conversations.map((c) =>
              c.conversation_id === res.conversation_id
                ? {
                    ...c,
                    last_activity: new Date().toISOString(),
                    message_count: c.message_count + 2,
                  }
                : c,
            )
          : [
              {
                conversation_id: res.conversation_id,
                title: message.slice(0, 60),
                started_at: new Date().toISOString(),
                last_activity: new Date().toISOString(),
                status: "active" as const,
                message_count: 2,
              },
              ...s.conversations,
            ];

        return {
          messages: updated,
          activeConversationId: res.conversation_id,
          isLoading: false,
          conversations: updatedConvos,
        };
      });

      return res.conversation_id;
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : "Failed to send message.";
      set((s) => {
        // Remove loading/optimistic bubbles on error
        const msgs = (s.messages[cid] ?? []).filter(
          (m) => !m.isLoading && !m.isOptimistic,
        );
        return {
          isLoading: false,
          error: errMsg,
          messages: { ...s.messages, [cid]: msgs },
        };
      });
      return null;
    }
  },

  streamMessage: async (message, conversationId, onConversationId) => {
    const tempId = `optimistic-${Date.now()}`;
    const loadingId = `loading-${Date.now()}`;
    const userMsg: OptimisticMessage = {
      message_id: tempId,
      role: "user",
      content: message,
      structured_response: null,
      created_at: new Date().toISOString(),
      isOptimistic: true,
      isLoading: false,
    };
    const loadingMsg: OptimisticMessage = {
      message_id: loadingId,
      role: "assistant",
      content: "",
      structured_response: null,
      created_at: new Date().toISOString(),
      isOptimistic: true,
      isLoading: true,
    };

    const cid = conversationId ?? "new";

    set((s) => ({
      isLoading: true,
      error: null,
      messages: {
        ...s.messages,
        [cid]: [...(s.messages[cid] ?? []), userMsg, loadingMsg],
      },
    }));

    // Helper: patch one message in a messages array by id
    const patchMsg = (
      msgs: OptimisticMessage[],
      id: string,
      patch: Partial<OptimisticMessage>,
    ): OptimisticMessage[] =>
      msgs.map((m) => (m.message_id === id ? { ...m, ...patch } : m));

    let resolvedCid = cid;

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Stream request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep last (potentially incomplete) line in buffer
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let event: Record<string, unknown>;
          try {
            event = JSON.parse(raw);
          } catch {
            continue; // malformed line — skip
          }

          const type = event.type as string;

          if (type === "conversation_ready") {
            // New conversation: update the key we track messages under and
            // fire the navigation callback so the URL updates immediately.
            const newCid = event.conversation_id as string;
            if (newCid !== cid) {
              set((s) => {
                const existing = s.messages[cid] ?? [];
                const updated = { ...s.messages };
                delete updated[cid];
                updated[newCid] = existing;
                return { messages: updated };
              });
              resolvedCid = newCid;
            }
            onConversationId?.(newCid);
          } else if (type === "node_start") {
            const node = event.node as string;
            set((s) => ({
              messages: {
                ...s.messages,
                [resolvedCid]: patchMsg(
                  s.messages[resolvedCid] ?? [],
                  loadingId,
                  { currentNode: node },
                ),
              },
            }));
          } else if (type === "done") {
            // Build the final assistant message from the SSE payload
            const res = event as {
              conversation_id: string;
              message_id: string;
              intent: string;
              status: string;
              response: OptimisticMessage["structured_response"];
            };

            const assistantMsg: OptimisticMessage = {
              message_id: res.message_id,
              role: "assistant",
              content: (res.response as { summary?: string })?.summary ?? "",
              structured_response: res.response,
              created_at: new Date().toISOString(),
              intent: res.intent as OptimisticMessage["intent"],
              isOptimistic: false,
              isLoading: false,
            };

            const finalCid = res.conversation_id;
            set((s) => {
              const existing = s.messages[finalCid] ?? [];
              // Remove the loading bubble, keep real messages
              const withoutLoading = existing.filter((m) => !m.isLoading);
              // Mark the optimistic user bubble as confirmed
              const confirmed = withoutLoading.map((m) =>
                m.message_id === tempId ? { ...m, isOptimistic: false } : m,
              );
              confirmed.push(assistantMsg);

              const conv = s.conversations.find(
                (c) => c.conversation_id === finalCid,
              );
              const updatedConvos = conv
                ? s.conversations.map((c) =>
                    c.conversation_id === finalCid
                      ? {
                          ...c,
                          last_activity: new Date().toISOString(),
                          message_count: c.message_count + 2,
                        }
                      : c,
                  )
                : [
                    {
                      conversation_id: finalCid,
                      title: message.slice(0, 60),
                      started_at: new Date().toISOString(),
                      last_activity: new Date().toISOString(),
                      status: "active" as const,
                      message_count: 2,
                    },
                    ...s.conversations,
                  ];

              return {
                messages: { ...s.messages, [finalCid]: confirmed },
                activeConversationId: finalCid,
                isLoading: false,
                conversations: updatedConvos,
              };
            });

            return res.conversation_id;
          } else if (type === "error") {
            throw new Error((event.message as string) ?? "Streaming error");
          }
        }
      }

      // Stream ended without a "done" event — treat as error
      throw new Error("Stream closed without a response");
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : "Failed to send message.";
      set((s) => {
        const msgs = (s.messages[resolvedCid] ?? []).filter(
          (m) => !m.isLoading && !m.isOptimistic,
        );
        return {
          isLoading: false,
          error: errMsg,
          messages: {
            ...s.messages,
            [resolvedCid]: msgs,
          },
        };
      });
      return null;
    }
  },

  injectSystemMessage: (conversationId, content) => {
    const msg: OptimisticMessage = {
      message_id: `system-${Date.now()}`,
      role: "assistant",
      content,
      structured_response: null,
      created_at: new Date().toISOString(),
      isOptimistic: true,
      isLoading: false,
      isSystemEvent: true,
    };
    set((s) => ({
      messages: {
        ...s.messages,
        [conversationId]: [...(s.messages[conversationId] ?? []), msg],
      },
    }));
  },

  renameConversation: async (id, title) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    // Optimistic update
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.conversation_id === id ? { ...c, title: trimmed } : c,
      ),
    }));
    try {
      await chatApi.updateConversationTitle(id, trimmed);
    } catch {
      // Reload list to restore server state on failure
      try {
        const data = await chatApi.getConversations();
        set({ conversations: data.conversations });
      } catch {
        /* silent */
      }
      set({ error: "Failed to rename conversation." });
    }
  },

  archiveConversation: async (id) => {
    try {
      await chatApi.deleteConversation(id);
      set((s) => {
        const msgs = { ...s.messages };
        delete msgs[id];
        return {
          conversations: s.conversations.filter(
            (c) => c.conversation_id !== id,
          ),
          messages: msgs,
          activeConversationId:
            s.activeConversationId === id ? null : s.activeConversationId,
        };
      });
    } catch {
      set({ error: "Failed to archive conversation." });
    }
  },
}));
