import { get, post, del, patch } from "./client";
import type {
  ChatRequest,
  ChatResponse,
  ConversationSummary,
  ConversationDetail,
} from "../types/api";

export const sendMessage = (body: ChatRequest): Promise<ChatResponse> =>
  post<ChatResponse>("/api/chat", body);

export const getConversations = async (): Promise<{
  conversations: ConversationSummary[];
}> => {
  const list = await get<ConversationSummary[]>("/api/conversations");
  return { conversations: Array.isArray(list) ? list : [] };
};

export const getConversation = (id: string): Promise<ConversationDetail> =>
  get<ConversationDetail>(`/api/conversations/${id}`);

export const deleteConversation = (id: string): Promise<void> =>
  del(`/api/conversations/${id}`);

export const updateConversationTitle = (
  id: string,
  title: string,
): Promise<{ conversation_id: string; title: string }> =>
  patch(`/api/conversations/${id}`, { title });
