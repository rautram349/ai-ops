import { useState, useRef, useCallback } from "react";
import { ArrowUp, Loader2, Sparkles } from "lucide-react";
import { Button } from "../ui/Button";

interface ChatInputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
  sticky?: boolean;
}

export function ChatInputBar({
  onSend,
  disabled = false,
  isLoading = false,
  sticky = true,
}: ChatInputBarProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text || disabled || isLoading) return;
    onSend(text);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, disabled, isLoading, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const canSend = value.trim().length > 0 && !disabled && !isLoading;

  return (
    <div className={[sticky ? "sticky bottom-0 z-10" : "relative", "shrink-0"].join(" ")}>
      <div
        className="chat-content"
        style={{
          paddingTop: sticky ? "16px" : "10px",
          paddingBottom: sticky ? "16px" : "22px",
        }}
      >
        <div
          className="surface-card flex items-end gap-3 transition-all duration-200"
          style={{
            padding: "12px 14px",
            borderColor: focused ? "var(--accent)" : undefined,
            boxShadow: focused
              ? "0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent)"
              : "var(--shadow-sm)",
          }}
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el)">
            <Sparkles size={14} style={{ color: "var(--accent)" }} />
          </div>

          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            disabled={disabled || isLoading}
            placeholder="Ask about revenue, inventory, campaigns, or support?"
            className="max-h-40 flex-1 resize-none overflow-y-auto bg-transparent text-sm leading-relaxed outline-none disabled:cursor-not-allowed"
            style={{
              color: "var(--text-pri)",
              minHeight: "30px",
              padding: "0",
              border: "none",
              outline: "none",
              boxShadow: "none",
              overflowWrap: "break-word",
              wordBreak: "break-word",
            }}
          />

          <Button
            onClick={handleSend}
            disabled={!canSend}
            variant="primary"
            size="sm"
            className="h-10 min-w-10 rounded-[var(--radius-sm)] px-3"
          >
            {isLoading ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}
          </Button>
        </div>

        {sticky && (
          <p className="mt-2 text-center text-meta">
            <kbd style={{ fontFamily: "inherit", fontWeight: 500 }}>Enter</kbd> to send
            <span style={{ margin: "0 6px", color: "var(--border-h)" }}>?</span>
            <kbd style={{ fontFamily: "inherit", fontWeight: 500 }}>Shift+Enter</kbd> for newline
          </p>
        )}
      </div>
    </div>
  );
}
