import { useEffect, useRef } from "react";

import { useGetBlackboardQuery } from "../app/api";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { agentSaid } from "../features/agents/agentsChatSlice";
import { DEMO_ROSTER } from "../features/agents/arrogantLines";
import { clearLearnItems, learnItemReceived, type LearnKind } from "../features/learn/learnSlice";

function valueText(value: unknown): string {
  if (typeof value === "object" && value !== null && "text" in value) {
    return String(Reflect.get(value, "text"));
  }
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function classify(section: string, key: string, _value: unknown): LearnKind | null {
  if (section === "discoveries") return "discovery";
  if (section === "lessons") {
    if (key.startsWith("feedback.")) return "outcome";
    return "lesson";
  }
  return null;
}

function valueOk(value: unknown): boolean | null {
  if (typeof value !== "object" || value === null || !("ok" in value)) return null;
  const ok = Reflect.get(value, "ok");
  return typeof ok === "boolean" ? ok : null;
}

function valueActionId(value: unknown): string | null {
  if (typeof value !== "object" || value === null || !("action_id" in value)) return null;
  const actionId = Reflect.get(value, "action_id");
  return typeof actionId === "string" && actionId.length > 0 ? actionId : null;
}

/** Poll session blackboard: crew chat + Ops Center learn-loop strip. */
export function useBlackboardAgents(): void {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const seen = useRef(new Set<string>());
  const { data } = useGetBlackboardQuery(
    { sessionId: sessionId ?? "", sinceVersion: undefined },
    { skip: !sessionId, pollingInterval: 2500 },
  );

  useEffect(() => {
    seen.current.clear();
    dispatch(clearLearnItems());
  }, [dispatch, sessionId]);

  useEffect(() => {
    if (!data?.entries.length) return;
    for (const row of data.entries) {
      const agentSection =
        row.section === "notes" ||
        row.section === "goals" ||
        row.section === "discoveries" ||
        row.section === "lessons" ||
        row.section === "hypotheses";
      if (!agentSection) continue;
      if (typeof row.author !== "string" || !row.author.startsWith("agent:")) continue;
      const key = `${row.section}:${row.key}:${JSON.stringify(row.value)}`;
      if (seen.current.has(key)) continue;
      seen.current.add(key);
      const text = valueText(row.value);
      if (!text.trim()) continue;

      const learnKind = classify(row.section, row.key, row.value);
      if (learnKind) {
        dispatch(
          learnItemReceived({
            key: `${row.section}:${row.key}`,
            kind: learnKind,
            text,
            ok: valueOk(row.value),
            actionId: valueActionId(row.value),
          }),
        );
      }

      const author = typeof row.author === "string" ? row.author : "agent";
      const slug = author.includes(":") ? (author.split(":").pop() ?? "wernher") : "wernher";
      const roster = DEMO_ROSTER.find((a) => a.persona_slug === slug) ?? DEMO_ROSTER[0];
      if (!roster) continue;
      const prefix =
        learnKind === "outcome"
          ? valueOk(row.value) === false
            ? "[outcome fail] "
            : "[outcome] "
          : learnKind === "lesson"
            ? "[lesson] "
            : learnKind === "discovery"
              ? "[discovery] "
              : "";
      dispatch(
        agentSaid({
          persona_slug: roster.persona_slug,
          display_name: roster.display_name,
          role: roster.role,
          text: `${prefix}${text}`,
        }),
      );
    }
  }, [data, dispatch]);
}
