import Box from "@mui/material/Box";
import { AgentAvatar, roleColor } from "@titan/ui-kit";
import { useState } from "react";

import { portraitUrl } from "../../services/avatar/portrait";

export interface AgentPortraitProps {
  personaSlug: string;
  displayName: string;
  role: string;
  size?: number;
  speaking?: boolean;
  muted?: boolean;
  /** Protocol/live override when the bus supplies portrait_url. */
  overrideUrl?: string | null;
}

/**
 * Live Ops Center portrait: ComfyUI (or static) image with initials fallback.
 */
export function AgentPortrait({
  personaSlug,
  displayName,
  role,
  size = 28,
  speaking = false,
  muted = false,
  overrideUrl,
}: AgentPortraitProps) {
  const src = portraitUrl(personaSlug, overrideUrl);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = failedSrc === src;

  if (failed) {
    return <AgentAvatar name={displayName} role={role} size={size} speaking={speaking} muted={muted} />;
  }

  const ring = roleColor(role);
  return (
    <Box
      component="img"
      src={src}
      alt=""
      aria-hidden
      onError={() => {
        setFailedSrc(src);
      }}
      sx={{
        width: size,
        height: size,
        borderRadius: "50%",
        objectFit: "cover",
        flexShrink: 0,
        opacity: muted ? 0.45 : 1,
        boxShadow: speaking ? `0 0 0 2px ${ring}` : "none",
        transition: "box-shadow 120ms ease-out, opacity 120ms ease-out",
      }}
    />
  );
}
