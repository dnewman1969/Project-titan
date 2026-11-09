/** Demo banter until live bus chat is wired (M7.T2). */

export interface RosterEntry {
  persona_slug: string;
  display_name: string;
  role: string;
}

export type BanterKind = "greeting" | "feast" | "insult" | "incredible";

/** Appendix A KSP Mission Control — demo roster until live bus (M7.T2). */
export const DEMO_ROSTER: readonly RosterEntry[] = [
  { persona_slug: "wernher", display_name: "Wernher", role: "director" },
  { persona_slug: "gene", display_name: "Gene", role: "flight_engineer" },
  { persona_slug: "linus", display_name: "Linus", role: "mission_planner" },
  { persona_slug: "val", display_name: "Val", role: "navigator" },
  { persona_slug: "jeb-radio", display_name: "Jeb Radio", role: "commentator.host" },
];

const SMACK: Record<BanterKind, string[]> = {
  greeting: [
    "Oh. You're here. Try not to touch anything labeled 'staging'—I already optimized it.",
    "Welcome back, human. I'll carry the mission; you carry the snacks.",
  ],
  feast: [
    "I solved that in one pass. You're welcome. Try to keep up.",
    "Another flawless maneuver. Maybe screenshot it—you'll want proof I was right.",
    "That wasn't luck. That was me. Document it for your memoir.",
  ],
  insult: [
    "Cute attempt. Here's what you should have done instead.",
    "I've seen slower reaction times in wet cement. Listen closely this time.",
    "You call that a plan? Adorable. Watch a professional.",
  ],
  incredible: [
    "Orbit achieved. You may clap. Quietly.",
    "Fine unlocked. I make impossible look routine—get used to it.",
    "Perfect burn. NASA wishes they had my telemetry feed.",
  ],
};

export function pickBanterLine(kind: BanterKind, agent: RosterEntry): string {
  const pool = SMACK[kind];
  const line = pool[Math.floor(Math.random() * pool.length)] ?? pool[0] ?? "";
  return `${agent.display_name}: ${line}`;
}

export const OWL_VOICE_BY_ROLE: Record<string, string> = {
  director: "Onyx",
  flight_engineer: "Echo",
  mission_planner: "Sage",
  navigator: "Nova",
  "commentator.host": "Fable",
};
