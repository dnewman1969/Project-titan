/** Vite booleans default off unless the env explicitly enables them (true / 1). */
export function viteEnvEnabled(raw: string | boolean | undefined): boolean {
  if (raw === true) return true;
  if (typeof raw !== "string") return false;
  const v = raw.trim().toLowerCase();
  return v === "true" || v === "1";
}

export function autoDemoEnabled(): boolean {
  return viteEnvEnabled(import.meta.env.VITE_TITAN_AUTO_DEMO);
}
