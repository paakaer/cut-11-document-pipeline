export const pct = (x: number | null | undefined, digits = 1) => (x == null ? "–" : `${(x * 100).toFixed(digits)}%`);

export const fmtUsd = (x: number) => (x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(3)}`);

export const fmtEur = (x: number | null | undefined) =>
  x == null ? "–" : x < 0.01 ? `€${x.toFixed(4)}` : `€${x.toFixed(3)}`;
