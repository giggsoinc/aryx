/**
 * Simulated streaming: reveals a finished text response token-by-token.
 * Real SSE comes later when the backend grows a streaming endpoint —
 * this hook is the placeholder UX so the chat feels alive today.
 */
export function streamReveal(
  text: string,
  onChunk: (full: string) => void,
  opts: { msPerChunk?: number; chunkSize?: number } = {},
): { cancel: () => void } {
  const msPerChunk = opts.msPerChunk ?? 22;
  const chunkSize = opts.chunkSize ?? 4;
  let i = 0;
  let cancelled = false;
  const tick = () => {
    if (cancelled) return;
    i = Math.min(i + chunkSize, text.length);
    onChunk(text.slice(0, i));
    if (i < text.length) setTimeout(tick, msPerChunk);
  };
  tick();
  return {
    cancel: () => {
      cancelled = true;
    },
  };
}
