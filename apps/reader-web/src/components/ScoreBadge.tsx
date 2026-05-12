export function ScoreBadge({ label, value }: { label: string; value: number | null }) {
  const display = value === null ? "--" : String(value);
  return (
    <span className="scoreBadge" title={label}>
      <span>{label}</span>
      <strong>{display}</strong>
    </span>
  );
}
