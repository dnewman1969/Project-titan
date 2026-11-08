import SendIcon from "@mui/icons-material/Send";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Typography from "@mui/material/Typography";
import type { ChatSender } from "@titan/protocol";
import { AgentAvatar, roleColor } from "@titan/ui-kit";

import { Panel } from "../operations/Panel";

type RosterEntry = Pick<ChatSender, "persona_slug" | "display_name" | "role">;

/** Appendix A KSP "Mission Control" team, shown as a preview until sessions spawn agents (M6.T6). */
export const PREVIEW_ROSTER: readonly RosterEntry[] = [
  { persona_slug: "wernher", display_name: "Wernher", role: "director" },
  { persona_slug: "gene", display_name: "Gene", role: "flight_engineer" },
  { persona_slug: "linus", display_name: "Linus", role: "mission_planner" },
  { persona_slug: "val", display_name: "Val", role: "navigator" },
  { persona_slug: "jeb-radio", display_name: "Jeb Radio", role: "commentator.host" },
];

export function AgentsPanel() {
  return (
    <Panel title="AI Agents" subtitle="Mission Control (preview)" gridArea="agents" flush>
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
          }}
        >
          {PREVIEW_ROSTER.map((agent) => (
            <Chip
              role="listitem"
              key={agent.persona_slug}
              avatar={<AgentAvatar name={agent.display_name} role={agent.role} size={22} muted />}
              label={agent.display_name}
              variant="outlined"
              sx={{ borderColor: roleColor(agent.role), opacity: 0.7 }}
            />
          ))}
        </Box>
        <Box
          role="log"
          aria-label="Agent chat"
          sx={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", px: 3, textAlign: "center" }}
        >
          <Box>
            <Typography variant="body2" color="text.secondary">
              The crew joins when a session starts.
            </Typography>
            <Typography variant="caption" color="text.disabled">
              Streaming chat, event chips and @mentions arrive in M7.T2.
            </Typography>
          </Box>
        </Box>
        <Box
          component="form"
          onSubmit={(e) => {
            e.preventDefault();
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
            disabled
            fullWidth
            placeholder="Message the crew..."
            inputProps={{ "aria-label": "Message the crew" }}
          />
          <IconButton type="submit" disabled aria-label="Send" size="small">
            <SendIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    </Panel>
  );
}
