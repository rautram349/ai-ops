import type { OptimisticMessage } from "../../types/api";

interface UserMessageProps {
  message: OptimisticMessage;
}

export function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end animate-fade-in">
      <div
        className="max-w-[82%] rounded-[var(--radius-lg)] border text-sm leading-relaxed md:max-w-[75%]"
        style={{
          padding: "14px 18px",
          background: "var(--chat-message-user-bg)",
          borderColor: "var(--chat-message-user-border)",
          color: "var(--text-pri)",
          opacity: message.isOptimistic ? 0.75 : 1,
          boxShadow: message.isOptimistic ? "none" : "var(--shadow-sm)",
          whiteSpace: "pre-wrap",
          wordWrap: "break-word",
          overflowWrap: "break-word",
          wordBreak: "break-word",
          overflow: "hidden",
        }}
      >
        {message.content}
      </div>
    </div>
  );
}
