import type { RecommendedAction } from "../../../types/api";
import { ActionCard } from "./ActionCard";

export function RecommendationList({
  recommendations,
}: {
  recommendations: RecommendedAction[];
}) {
  if (!recommendations.length) return null;
  return (
    <div className="flex flex-col gap-3">
      {recommendations.map((r, i) => (
        <ActionCard key={i} action={r} />
      ))}
    </div>
  );
}
