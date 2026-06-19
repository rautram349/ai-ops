import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import {
  MessageSquare,
  Plus,
  CheckSquare,
  AlertTriangle,
  Trash2,
  Pencil,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useChatStore } from "../../stores/chatStore";
import { useApprovalStore } from "../../stores/approvalStore";
import { useMonitorStore } from "../../stores/monitorStore";
import { formatRelative } from "../../lib/format";
import { Button } from "../ui/Button";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

function ConversationSkeleton() {
  return (
    <div className="flex flex-col gap-3" style={{ paddingBottom: "8px" }}>
      {[75, 55, 65].map((w, i) => (
        <div key={i} className="flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-3">
          <div className="skeleton h-3 w-3 rounded-sm shrink-0" />
          <div className="flex flex-1 flex-col gap-1.5">
            <div className="skeleton h-2.5 rounded" style={{ width: `${w}%` }} />
            <div className="skeleton h-2 w-2/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const navigate = useNavigate();
  const {
    conversations,
    activeConversationId,
    isLoading,
    loadConversationList,
    archiveConversation,
    renameConversation,
    setActiveConversation,
  } = useChatStore();
  const { pendingCount, fetchApprovals } = useApprovalStore();
  const { newIncidentCount, startPolling, markViewed } = useMonitorStore();
  const initialized = useRef(false);

  const revealText = (maxWidth: number): CSSProperties => ({
    maxWidth: collapsed ? 0 : `${maxWidth}px`,
    opacity: collapsed ? 0 : 1,
    overflow: "hidden",
    whiteSpace: "nowrap",
    transform: collapsed ? "translateX(-8px)" : "translateX(0)",
    transition: "max-width 220ms ease, opacity 180ms ease, transform 220ms ease",
  });

  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true;
      loadConversationList();
      fetchApprovals("pending");
      const stopPolling = startPolling();
      return stopPolling;
    }
  }, [loadConversationList, fetchApprovals, startPolling]);

  const handleNewChat = () => {
    setActiveConversation(null);
    navigate("/chat");
  };

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const handleRenameClick = (
    e: React.MouseEvent,
    id: string,
    currentTitle: string,
  ) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingId(id);
    setEditingTitle(currentTitle);
  };

  const handleRenameSave = async (id: string, originalTitle: string) => {
    const trimmed = editingTitle.trim();
    setEditingId(null);
    if (trimmed && trimmed !== originalTitle) {
      await renameConversation(id, trimmed);
    }
  };

  const handleDeleteClick = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    setConfirmDeleteId(id);
  };

  const handleConfirmDelete = async () => {
    if (!confirmDeleteId) return;
    const id = confirmDeleteId;
    setConfirmDeleteId(null);
    await archiveConversation(id);
    if (activeConversationId === id) navigate("/chat");
  };

  return (
    <aside
      style={{
        width: "var(--sidebar-width)",
        background: "var(--surface-raised)",
        borderRight: "1px solid var(--border)",
      }}
      className="relative flex h-full shrink-0 flex-col overflow-hidden transition-[width] duration-300 ease-out"
    >
      <div
        className="hairline-x"
        style={{
          padding: collapsed ? "16px 0" : "18px 18px 16px",
          display: "flex",
          flexDirection: collapsed ? "column" : "row",
          alignItems: "center",
          justifyContent: collapsed ? "center" : "space-between",
          gap: collapsed ? "4px" : "10px",
        }}
      >
        <Link
          to="/chat"
          className="group flex min-w-0 items-center overflow-hidden"
          title="AI-ops"
          style={{
            flex: collapsed ? "0 0 auto" : "1 1 auto",
            gap: collapsed ? "0px" : "12px",
          }}
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-(--border) bg-(--surface-el)">
            <BrainCircuit size={16} style={{ color: "var(--accent)" }} />
          </div>
          <div style={revealText(180)}>
            <p
              style={{
                color: "var(--text-pri)",
                fontWeight: 700,
                fontSize: "var(--text-md)",
                letterSpacing: "-0.02em",
              }}
            >
              AI-ops
            </p>
          </div>
        </Link>

        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-(--text-ter) transition-all duration-150 hover:bg-(--surface-el) hover:text-(--text-pri)"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <div className="hairline-x px-3.5 py-4">
        <Button
          onClick={handleNewChat}
          variant="secondary"
          size="md"
          className="w-full justify-start"
          title="New chat"
        >
          <Plus size={14} className="shrink-0" />
          <span style={revealText(120)}>New chat</span>
        </Button>
      </div>

      {!collapsed && (
        <div className="mt-1.5 flex-1 overflow-y-auto px-3.5 pb-3.5">
          <p className="eyebrow px-2.5 py-2.5">Recent</p>

          {isLoading && !conversations.length ? (
            <ConversationSkeleton />
          ) : conversations.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-3 py-8">
              <MessageSquare size={20} style={{ color: "var(--text-ter)" }} />
              <p style={{ color: "var(--text-ter)", fontSize: "var(--text-xs)" }}>
                No conversations yet
              </p>
            </div>
          ) : (
            conversations.map((c, idx) => {
              const isActive = c.conversation_id === activeConversationId;
              return (
                <NavLink
                  key={c.conversation_id}
                  to={`/chat/${c.conversation_id}`}
                  className={[
                    "group relative mb-1 flex w-full items-start gap-2.5 overflow-hidden rounded-[var(--radius-md)] px-3 py-3 transition-all duration-150",
                    isActive
                      ? "text-(--text-pri)"
                      : "text-(--text-sec) hover:bg-(--surface-el) hover:text-(--text-pri)",
                  ].join(" ")}
                  style={{ animationDelay: `${idx * 40}ms` }}
                >
                  {isActive && (
                    <div
                      className="absolute left-0 top-2 bottom-2 w-px rounded-r"
                      style={{ background: "var(--accent)" }}
                    />
                  )}
                  <MessageSquare
                    size={12}
                    className="mt-1 shrink-0"
                    style={{ color: isActive ? "var(--text-pri)" : "var(--text-ter)" }}
                  />
                  <div className="min-w-0 flex-1">
                    {editingId === c.conversation_id ? (
                      <input
                        autoFocus
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onBlur={() => handleRenameSave(c.conversation_id, c.title)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRenameSave(c.conversation_id, c.title);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        onClick={(e) => e.preventDefault()}
                        className="w-full rounded px-1 leading-snug"
                        style={{
                          fontSize: "var(--text-sm)",
                          fontWeight: isActive ? 500 : 400,
                          color: "var(--text-pri)",
                          background: "var(--surface-el)",
                          border: "1px solid var(--accent)",
                          outline: "none",
                        }}
                      />
                    ) : (
                      <p
                        className="truncate leading-snug"
                        style={{
                          fontSize: "var(--text-sm)",
                          fontWeight: isActive ? 600 : 500,
                          color: isActive ? "var(--text-pri)" : "inherit",
                        }}
                      >
                        {c.title}
                      </p>
                    )}
                    <p className="text-meta mt-0.5">{formatRelative(c.last_activity)}</p>
                  </div>

                  <button
                    onClick={(e) => handleRenameClick(e, c.conversation_id, c.title)}
                    className="shrink-0 rounded-[var(--radius-sm)] p-1 opacity-0 transition-all duration-150 group-hover:opacity-100 text-(--text-ter) hover:bg-(--surface) hover:text-(--accent)"
                    title="Rename conversation"
                  >
                    <Pencil size={13} />
                  </button>

                  <button
                    onClick={(e) => handleDeleteClick(e, c.conversation_id)}
                    className="shrink-0 rounded-[var(--radius-sm)] p-1 opacity-0 transition-all duration-150 group-hover:opacity-100 text-(--text-ter) hover:bg-(--surface) hover:text-(--risk-high)"
                    title="Delete conversation"
                  >
                    <Trash2 size={14} />
                  </button>
                </NavLink>
              );
            })
          )}
        </div>
      )}

      {collapsed && <div className="flex-1" />}

      <div className="hairline-x flex flex-col gap-0.5 px-3.5 py-3.5" style={{ borderBottom: "none" }}>
        {[
          {
            to: "/approvals",
            Icon: CheckSquare,
            label: "Approvals",
            badge: pendingCount,
          },
          {
            to: "/incidents",
            Icon: AlertTriangle,
            label: "Incidents",
            badge: newIncidentCount,
            onNavigate: markViewed,
          },
        ].map(({ to, Icon, label, badge, onNavigate }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              [
                "relative flex items-center rounded-[var(--radius-md)] transition-all duration-150",
                isActive
                  ? "text-(--text-pri)"
                  : "text-(--text-sec) hover:bg-(--surface-el) hover:text-(--text-pri)",
              ].join(" ")
            }
            style={{
              justifyContent: collapsed ? "center" : "flex-start",
              gap: collapsed ? "0px" : "10px",
              minHeight: "42px",
              padding: collapsed ? "10px" : "10px 14px",
              fontSize: "var(--text-sm)",
              fontWeight: 500,
            }}
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div
                    className="absolute left-0 top-2 bottom-2 w-px rounded-r"
                    style={{ background: "var(--accent)" }}
                  />
                )}
                <Icon size={14} className="shrink-0" style={{ color: isActive ? "var(--text-pri)" : undefined }} />
                <span className="flex-1" style={revealText(120)}>
                  {label}
                </span>
                {badge > 0 && (
                  <span
                    className="flex h-5 w-5 items-center justify-center rounded-full border text-white font-bold"
                    style={{
                      fontSize: "var(--text-2xs)",
                      background: "var(--risk-high)",
                      borderColor: "transparent",
                      minWidth: "20px",
                      opacity: collapsed ? 0 : 1,
                      transform: collapsed ? "scale(0.8)" : "scale(1)",
                      transition: "opacity 180ms ease, transform 180ms ease",
                    }}
                  >
                    {badge > 9 ? "9+" : badge}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </div>

      {confirmDeleteId && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center"
          style={{ background: "var(--overlay-backdrop)", backdropFilter: "blur(4px)" }}
          onClick={() => setConfirmDeleteId(null)}
        >
          <div
            className="surface-card-lg w-[85%] max-w-[280px]"
            style={{ padding: "22px" }}
            onClick={(e) => e.stopPropagation()}
          >
            <p
              style={{
                color: "var(--text-pri)",
                fontSize: "0.85rem",
                fontWeight: 600,
                marginBottom: "6px",
              }}
            >
              Delete conversation?
            </p>
            <p
              style={{
                color: "var(--text-ter)",
                fontSize: "var(--text-xs)",
                lineHeight: 1.5,
                marginBottom: "16px",
              }}
            >
              This action cannot be undone.
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" className="flex-1" onClick={() => setConfirmDeleteId(null)}>
                Cancel
              </Button>
              <Button variant="danger" size="sm" className="flex-1" onClick={handleConfirmDelete}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
