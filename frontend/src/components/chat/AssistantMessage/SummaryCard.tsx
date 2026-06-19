import ReactMarkdown from "react-markdown";

interface SummaryCardProps {
  summary: string;
}

export function SummaryCard({ summary }: SummaryCardProps) {
  return (
    <div style={{ overflow: "hidden", wordBreak: "break-word" }}>
      <div
        className="prose max-w-none"
        style={{
          color: "var(--text-sec)",
          fontSize: "var(--text-base)",
          lineHeight: 1.75,
        }}
      >
        <ReactMarkdown>{summary}</ReactMarkdown>
      </div>
    </div>
  );
}
