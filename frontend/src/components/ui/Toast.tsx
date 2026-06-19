/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "info";

interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
}

let listeners: Array<(toasts: ToastMessage[]) => void> = [];
let toasts: ToastMessage[] = [];

function notify(nextToasts: ToastMessage[]) {
  listeners.forEach((fn) => fn([...nextToasts]));
}

export function showToast(message: string, type: ToastType = "info") {
  const id = `toast-${Date.now()}-${Math.random()}`;
  toasts = [...toasts, { id, type, message }];
  notify(toasts);
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    notify(toasts);
  }, 4000);
}

const icons = {
  success: <CheckCircle2 size={15} />,
  error: <AlertCircle size={15} />,
  info: <Info size={15} />,
};

const colors: Record<ToastType, string> = {
  success: "border-(--risk-low-border) text-(--risk-low)",
  error: "border-(--risk-high-border) text-(--risk-high)",
  info: "border-(--accent-border) text-(--accent)",
};

export function ToastContainer() {
  const [items, setItems] = useState<ToastMessage[]>([]);

  useEffect(() => {
    listeners.push(setItems);
    return () => {
      listeners = listeners.filter((l) => l !== setItems);
    };
  }, []);

  if (!items.length) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex max-w-[calc(100vw-2rem)] flex-col gap-2.5 sm:bottom-6 sm:right-6">
      {items.map((t) => (
        <div
          key={t.id}
          className={[
            "surface-card-lg animate-toast-in pointer-events-auto flex min-w-0 max-w-md items-center gap-3 px-4 py-3.5",
            "text-(--text-pri) text-(length:--text-sm) sm:min-w-72",
            colors[t.type],
          ].join(" ")}
        >
          <span className="shrink-0">{icons[t.type]}</span>
          <span className="flex-1 leading-relaxed text-(--text-pri)">{t.message}</span>
          <button
            className="shrink-0 text-(--text-sec) transition-colors hover:text-(--text-pri)"
            onClick={() => {
              toasts = toasts.filter((item) => item.id !== t.id);
              notify(toasts);
            }}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
