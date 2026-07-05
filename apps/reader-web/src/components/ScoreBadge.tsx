export function ScoreBadge({ label, value }: { label: string; value: number | string | null | undefined }) {
  const isEmpty = value == null || value === "";
  const display = isEmpty ? "未评" : String(value);
  return (
    <span className={isEmpty ? "scoreBadge scoreBadgeEmpty" : "scoreBadge"} title={label}>
      <span>{label}</span>
      <strong>{display}</strong>
    </span>
  );
}
