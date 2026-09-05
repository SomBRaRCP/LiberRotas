/** Formata uma diferença positiva com segundos para relógios regressivos. */
export function formatRemainingTime(targetTimeMs: number, referenceTimeMs: number) {
  const remainingSeconds = Math.max(0, Math.ceil((targetTimeMs - referenceTimeMs) / 1_000));
  if (remainingSeconds === 0) return "tempo encerrado";

  const days = Math.floor(remainingSeconds / 86_400);
  const hours = Math.floor((remainingSeconds % 86_400) / 3_600);
  const minutes = Math.floor((remainingSeconds % 3_600) / 60);
  const seconds = remainingSeconds % 60;

  if (days > 0) return `${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}min`;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}min ${String(seconds).padStart(2, "0")}s`;
  return `${minutes}min ${String(seconds).padStart(2, "0")}s`;
}

export function hasTimeEnded(targetTimeMs: number, referenceTimeMs: number) {
  return targetTimeMs <= referenceTimeMs;
}
