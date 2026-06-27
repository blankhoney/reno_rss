export function ScoreBadge({ label, value }: { label: string; value: number | string | null | undefined }) {
  const display = value == null || value === "" ? "未评" : String(value);
  return (
    <span className="scoreBadge" title={label}>
      <span>{label}</span>
      <strong>{display}</strong>
    </span>
  );
}
