"use client";

import { useEffect, useRef } from "react";

export interface TraceEvent {
  event: string;
  tool?: string;
  label?: string;
  args_preview?: string;
  duration_ms?: number | null;
  count?: number;
  decision?: string;
  status?: string;
  depth?: number;
  timestamp: number;
}

interface TracePanelProps {
  events: TraceEvent[];
  isOpen: boolean;
  onToggle: () => void;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function eventIcon(event: TraceEvent): { icon: string; color: string } {
  switch (event.event) {
    case "llm_call":
      return { icon: "cpu", color: "var(--trace-cyan)" };
    case "tool_call_start":
      if (event.tool === "tavily_search") return { icon: "search", color: "var(--trace-blue)" };
      if (event.tool === "write_script") return { icon: "edit", color: "var(--trace-purple)" };
      return { icon: "tool", color: "var(--trace-blue)" };
    case "tool_call_end":
      return { icon: "check", color: "var(--trace-green)" };
    case "sub_llm_call":
      return { icon: "cpu", color: "var(--trace-purple)" };
    case "interrupt":
      return { icon: "pause", color: "var(--trace-amber)" };
    case "resume":
      return { icon: "play", color: "var(--trace-green)" };
    default:
      return { icon: "dot", color: "var(--trace-muted)" };
  }
}

function eventLabel(event: TraceEvent): string {
  switch (event.event) {
    case "llm_call":
      return `LLM Call #${event.count}`;
    case "tool_call_start":
      if (event.tool === "tavily_search") {
        const query = event.args_preview || "";
        return `tavily_search: "${query.slice(0, 50)}${query.length > 50 ? "..." : ""}"`;
      }
      if (event.tool === "write_script") return "write_script";
      return `${event.tool}`;
    case "tool_call_end":
      if (event.duration_ms != null) {
        return `Done (${formatDuration(event.duration_ms)})`;
      }
      return "Done";
    case "sub_llm_call":
      if (event.duration_ms != null) {
        return `${event.label || "Sub-LLM"} (${formatDuration(event.duration_ms)})`;
      }
      return event.label || "Sub-LLM";
    case "interrupt":
      return "Awaiting approval";
    case "resume":
      if (event.decision === "approve") return "Approved";
      if (event.decision === "reject") return "Rejected -- replanning";
      if (event.decision === "edit") return "Edited";
      return `Resumed (${event.decision})`;
    default:
      return event.event;
  }
}

function IconSvg({ type }: { type: string }) {
  const props = { width: 14, height: 14, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

  switch (type) {
    case "search":
      return <svg {...props}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>;
    case "edit":
      return <svg {...props}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>;
    case "check":
      return <svg {...props}><polyline points="20 6 9 17 4 12" /></svg>;
    case "cpu":
      return <svg {...props}><rect x="4" y="4" width="16" height="16" rx="2" ry="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></svg>;
    case "pause":
      return <svg {...props}><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>;
    case "play":
      return <svg {...props}><polygon points="5 3 19 12 5 21 5 3" /></svg>;
    case "tool":
      return <svg {...props}><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>;
    default:
      return <svg {...props}><circle cx="12" cy="12" r="4" /></svg>;
  }
}

export default function TracePanel({ events, isOpen, onToggle }: TracePanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, isOpen]);

  const activeTools = events.filter(
    (e) => e.event === "tool_call_start" && !events.some(
      (end) => end.event === "tool_call_end" && end.tool === e.tool && end.timestamp > e.timestamp
    )
  );
  const isActive = activeTools.length > 0;

  return (
    <div className={`trace-panel ${isOpen ? "open" : "collapsed"}`}>
      <button className="trace-toggle" onClick={onToggle}>
        <div className="trace-toggle-left">
          <div className={`trace-indicator ${isActive ? "active" : events.length > 0 ? "done" : ""}`} />
          <span className="trace-toggle-label">Agent Trace</span>
          {events.length > 0 && (
            <span className="trace-count">{events.length}</span>
          )}
        </div>
        <svg
          className={`trace-chevron ${isOpen ? "" : "rotated"}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      {isOpen && (
        <div className="trace-body">
          {events.length === 0 ? (
            <div className="trace-empty">
              <div className="trace-empty-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <p>Agent activity will appear here</p>
            </div>
          ) : (
            <div className="trace-timeline">
              {events.map((evt, i) => {
                const { icon, color } = eventIcon(evt);
                const depth = evt.depth ?? 0;
                return (
                  <div
                    key={i}
                    className={`trace-event depth-${depth}`}
                    style={{ "--event-color": color } as React.CSSProperties}
                  >
                    <div className="trace-event-line" />
                    <div className="trace-event-dot">
                      <IconSvg type={icon} />
                    </div>
                    <div className="trace-event-content">
                      <span className="trace-event-label">{eventLabel(evt)}</span>
                      <span className="trace-event-time">{formatTime(evt.timestamp)}</span>
                    </div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
          )}

          {/* Live status bar at bottom */}
          {isActive && (
            <div className="trace-status">
              <div className="trace-status-dot" />
              <span>{eventLabel(activeTools[activeTools.length - 1])}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
