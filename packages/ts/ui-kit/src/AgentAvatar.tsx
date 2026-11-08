import Avatar from "@mui/material/Avatar";
import { alpha } from "@mui/material/styles";

import { roleColor } from "./theme";

export interface AgentAvatarProps {
  name: string;
  role: string;
  speaking?: boolean;
  muted?: boolean;
  size?: number;
}

export function initials(name: string): string {
  const words = name
    .replace(/["“”]/g, "")
    .split(/\s+/)
    .filter((w) => /\p{L}/u.test(w));
  const picked = words.length > 1 ? [words[0], words[words.length - 1]] : words;
  return picked
    .map((w) => (w ?? "").charAt(0).toUpperCase())
    .join("")
    .slice(0, 2);
}

export function AgentAvatar({ name, role, speaking = false, muted = false, size = 32 }: AgentAvatarProps) {
  const color = roleColor(role);
  return (
    <Avatar
      alt={name}
      aria-label={`${name}, ${role.replace(/[._]/g, " ")}${speaking ? ", speaking" : ""}${muted ? ", muted" : ""}`}
      data-speaking={speaking || undefined}
      sx={{
        width: size,
        height: size,
        fontSize: size * 0.4,
        fontWeight: 700,
        color: "#0b0e14",
        backgroundColor: color,
        opacity: muted ? 0.45 : 1,
        boxShadow: speaking ? `0 0 0 2px #0b0e14, 0 0 0 4px ${alpha(color, 0.85)}` : "none",
        transition: "box-shadow 120ms ease-out",
      }}
    >
      {initials(name)}
    </Avatar>
  );
}
