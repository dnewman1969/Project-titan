import { useEffect, useRef } from "react";

import { useGetBlackboardQuery } from "../app/api";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { agentSaid } from "../features/agents/agentsChatSlice";
import { DEMO_ROSTER } from "../features/agents/arrogantLines";

/** Poll session blackboard and surface agent chat lines in the crew panel (live session). */
export function useBlackboardAgents(): void {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const seen = useRef(new Set<string>());
  const { data } = useGetBlackboardQuery(
    { sessionId: sessionId ?? "", sinceVersion: undefined },
    { skip: !sessionId, pollingInterval: 4000 },
  );

  useEffect(() => {
    seen.current.clear();
  }, [sessionId]);

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
      const text =
        typeof row.value === "object" && row.value !== null && "text" in row.value
          ? String(Reflect.get(row.value, "text"))
          : typeof row.value === "string"
            ? row.value
            : JSON.stringify(row.value);
      if (!text.trim()) continue;
      const author = typeof row.author === "string" ? row.author : "agent";
      const slug = author.includes(":") ? (author.split(":").pop() ?? "wernher") : "wernher";
      const roster = DEMO_ROSTER.find((a) => a.persona_slug === slug) ?? DEMO_ROSTER[0];
      if (!roster) continue;
      dispatch(
        agentSaid({
          persona_slug: roster.persona_slug,
          display_name: roster.display_name,
          role: roster.role,
          text,
        }),
      );
    }
  }, [data, dispatch]);
}
