import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import SendIcon from "@mui/icons-material/Send";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { AgentAvatar, roleColor } from "@titan/ui-kit";
import { useCallback, useState, type FormEvent } from "react";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { portraitUrl } from "../../services/avatar/portrait";
import { speakAgentLine } from "../../services/voice/speak";
import { Panel } from "../operations/Panel";
import { agentSaid, setSpeaking } from "./agentsChatSlice";
import { OWL_VOICE_BY_ROLE, pickBanterLine, type BanterKind, type RosterEntry } from "./arrogantLines";

/** Appendix A KSP "Mission Control" team — demo chat + voice until live bus (M7.T2). */
export const PREVIEW_ROSTER: readonly RosterEntry[] = [
  { persona_slug: "wernher", display_name: "Wernher", role: "director" },
  { persona_slug: "gene", display_name: "Gene", role: "flight_engineer" },
  { persona_slug: "linus", display_name: "Linus", role: "mission_planner" },
  { persona_slug: "val", display_name: "Val", role: "navigator" },
  { persona_slug: "jeb-radio", display_name: "Jeb Radio", role: "commentator.host" },
];

export function AgentsPanel() {
  const dispatch = useAppDispatch();
  const lines = useAppSelector((s) => s.agentsChat.lines);
  const speakingSlug = useAppSelector((s) => s.agentsChat.speakingSlug);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const deliver = useCallback(
    async (agent: RosterEntry, text: string) => {
      dispatch(
        agentSaid({
          persona_slug: agent.persona_slug,
          display_name: agent.display_name,
          role: agent.role,
          text,
        }),
      );
      dispatch(setSpeaking(agent.persona_slug));
      setBusy(true);
      try {
        const voice = OWL_VOICE_BY_ROLE[agent.role] ?? "Onyx";
        await speakAgentLine(text, { voiceId: voice });
      } finally {
        dispatch(setSpeaking(null));
        setBusy(false);
      }
    },
    [dispatch],
  );

  const demoLine = async (kind: BanterKind) => {
    const fallback = PREVIEW_ROSTER[0];
    if (!fallback) return;
    const agent = PREVIEW_ROSTER[Math.floor(Math.random() * PREVIEW_ROSTER.length)] ?? fallback;
    const text = pickBanterLine(kind, agent);
    const body = text.includes(": ") ? text.split(": ").slice(1).join(": ") : text;
    await deliver(agent, body);
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || busy) return;
    setDraft("");
    const agent = PREVIEW_ROSTER[0];
    if (!agent) return;
    const reply =
      pickBanterLine("insult", agent).split(": ").slice(1).join(": ") +
      ` (You wrote: "${trimmed.slice(0, 80)}${trimmed.length > 80 ? "…" : ""}")`;
    await deliver(agent, reply);
  };

  return (
    <Panel title="AI Agents" subtitle="Mission Control" gridArea="agents" flush>
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box
          role="list"
          aria-label="Agent roster"
          sx={{
            display: "flex",
            gap: 1,
            px: 1.5,
            py: 1,
            borderBottom: 1,
            borderColor: "divider",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {PREVIEW_ROSTER.map((agent) => {
            const speaking = speakingSlug === agent.persona_slug;
            const src = portraitUrl(agent.persona_slug);
            return (
              <Chip
                role="listitem"
                key={agent.persona_slug}
                avatar={
                  src ? (
                    <Box
                      component="img"
                      src={src}
                      alt=""
                      onError={(ev) => {
                        (ev.target as HTMLImageElement).style.display = "none";
                      }}
                      sx={{
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        objectFit: "cover",
                        boxShadow: speaking ? `0 0 0 2px ${roleColor(agent.role)}` : "none",
                      }}
                    />
                  ) : (
                    <AgentAvatar
                      name={agent.display_name}
                      role={agent.role}
                      size={22}
                      speaking={speaking}
                      muted={!speaking && Boolean(speakingSlug)}
                    />
                  )
                }
                label={agent.display_name}
                variant="outlined"
                onClick={() => void demoLine("greeting")}
                sx={{
                  borderColor: roleColor(agent.role),
                  opacity: speaking ? 1 : 0.85,
                  cursor: "pointer",
                }}
              />
            );
          })}
        </Box>
        <Stack direction="row" spacing={1} sx={{ px: 1.5, py: 1, flexWrap: "wrap" }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<AutoAwesomeIcon />}
            disabled={busy}
            onClick={() => void demoLine("incredible")}
          >
            Brag
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<RecordVoiceOverIcon />}
            disabled={busy}
            onClick={() => void demoLine("insult")}
          >
            Roast me
          </Button>
        </Stack>
        <Box
          role="log"
          aria-label="Agent chat"
          aria-live="polite"
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            px: 1.5,
            py: 1,
            display: "flex",
            flexDirection: "column",
            gap: 1,
          }}
        >
          {lines.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", mt: 4 }}>
              Tap an agent or Brag / Roast me for a voice demo. Set VITE_OWL_TTS_URL for Owl TTS and
              VITE_COMFYUI_VIEW_URL for ComfyUI portraits.
            </Typography>
          ) : (
            lines.map((line) => (
              <Box key={line.id} sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                <AgentAvatar
                  name={line.display_name}
                  role={line.role}
                  size={28}
                  speaking={speakingSlug === line.persona_slug}
                />
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {line.display_name}
                  </Typography>
                  <Typography variant="body2">{line.text}</Typography>
                </Box>
              </Box>
            ))
          )}
        </Box>
        <Box
          component="form"
          onSubmit={(e) => {
            void onSubmit(e);
          }}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            m: 1,
            px: 1.5,
            py: 0.5,
            borderRadius: 2,
            bgcolor: "action.hover",
          }}
        >
          <InputBase
            fullWidth
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            placeholder="Message the crew… (they will judge you)"
            inputProps={{ "aria-label": "Message the crew" }}
          />
          <IconButton type="submit" disabled={busy || !draft.trim()} aria-label="Send" size="small">
            <SendIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    </Panel>
  );
}
