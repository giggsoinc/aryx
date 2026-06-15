// Deterministic colour per ontology type (by its index in the summary order).
// Used as inline styles since Tailwind can't generate dynamic class names.
export const TYPE_PALETTE = [
  "#4068A8", // steel/navy
  "#0E9488", // teal
  "#7C3AED", // violet
  "#E11D48", // rose
  "#D97706", // amber
  "#2D4B8A", // deep steel
  "#0891B2", // cyan
  "#DB2777", // pink
];

export function typeColor(index: number): string {
  return TYPE_PALETTE[index % TYPE_PALETTE.length];
}
