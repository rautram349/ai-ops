import { useState, type CSSProperties, type ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { ToastContainer } from "../ui/Toast";

interface MainLayoutProps {
  children: ReactNode;
}

const SIDEBAR_STORAGE_KEY = "ops-brain-sidebar-collapsed";

export function MainLayout({ children }: MainLayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  });

  const layoutStyle = {
    "--sidebar-width": isSidebarCollapsed ? "5.5rem" : "18.75rem",
  } as CSSProperties;

  const handleToggleSidebar = () => {
    setIsSidebarCollapsed((current) => {
      const next = !current;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      }
      return next;
    });
  };
  return (
    <div
      className="relative flex h-screen min-h-screen bg-(--bg)"
      style={layoutStyle}
    >
      <Sidebar
        collapsed={isSidebarCollapsed}
        onToggle={handleToggleSidebar}
      />
      <main className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>

      <ToastContainer />
    </div>
  );
}
