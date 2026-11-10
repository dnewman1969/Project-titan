import VideocamOffOutlinedIcon from "@mui/icons-material/VideocamOffOutlined";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Meter, StatusPill } from "@titan/ui-kit";
import { useEffect, useRef } from "react";

import { useGetObsCaptureStatusQuery, type ObsCaptureStatus } from "../../app/api";
import { Panel } from "../operations/Panel";

import { cameraBlockMessage, captureTrackViews } from "./devices";
import { useCaptureDevices } from "./useCaptureDevices";

function versionLabel(obs: ObsCaptureStatus | undefined): string {
  const versionRaw = obs?.version?.obsVersion ?? obs?.version?.obs_version;
  return typeof versionRaw === "string" || typeof versionRaw === "number" ? String(versionRaw) : "online";
}

function obsSubtitle(obs: ObsCaptureStatus | undefined, loading: boolean): string {
  if (!obs) return loading ? "Checking OBS…" : "OBS not running";
  if (obs.connected) {
    const version = versionLabel(obs);
    return obs.record?.active ? `OBS ${version} · recording` : `OBS ${version}`;
  }
  if (obs.state === "degraded") return obs.detail ?? "OBS handshake failed";
  return obs.detail ?? "OBS not running";
}

/** Webcam tile: OBSBOT Tiny preview, mic meter, and OBS record state. */
export function WebcamPanel() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { data: obs, isLoading, isError } = useGetObsCaptureStatusQuery(undefined, { pollingInterval: 5000 });
  const devices = useCaptureDevices();
  const webcam = obs?.webcam;
  const obsDevice =
    webcam?.selected === true && typeof webcam.device_name === "string" ? webcam.device_name : null;
  const cameraLabel = devices.cameraLabel ?? obsDevice;
  const obsConnected = obs?.connected === true;
  const obsRecording = obs?.record?.active === true;
  const rows = captureTrackViews({
    obsConnected,
    obsRecording,
    cameraLabel,
    micLive: devices.micLive,
  });
  const previewChip = devices.cameraStream
    ? (devices.cameraLabel ?? "Camera")
    : obsDevice
      ? `${obsDevice} in OBS`
      : "OBSBOT Tiny";
  const blocked =
    devices.cameraStream || !devices.cameraBlock ? null : cameraBlockMessage(devices.cameraBlock, obsDevice);

  useEffect(() => {
    const node = videoRef.current;
    if (!node) return;
    node.srcObject = devices.cameraStream;
    if (!devices.cameraStream || typeof node.play !== "function") return;
    const played: unknown = node.play();
    if (played instanceof Promise) {
      void played.catch(() => undefined);
    }
  }, [devices.cameraStream]);

  return (
    <Panel
      title="Webcam"
      subtitle={obsSubtitle(obs, isLoading && !isError)}
      gridArea="webcam"
      frame="content"
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 1.25,
          minWidth: 0,
        }}
      >
        <Box
          aria-label={devices.cameraStream ? undefined : "Webcam preview"}
          sx={{
            borderRadius: 2,
            border: 1,
            borderColor: "divider",
            bgcolor: "#0d1119",
            display: "grid",
            placeItems: "center",
            minHeight: 120,
            aspectRatio: "16 / 9",
            alignSelf: "start",
            overflow: "hidden",
            position: "relative",
          }}
        >
          {devices.cameraStream ? (
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              aria-label="Webcam preview"
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <Box sx={{ textAlign: "center", px: 2 }}>
              <VideocamOffOutlinedIcon sx={{ color: "text.disabled", fontSize: 36 }} />
              <Typography variant="body2" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
                {blocked ?? "OBSBOT Tiny not found."}
              </Typography>
            </Box>
          )}
          <Chip
            size="small"
            sx={{ position: "absolute", left: 8, bottom: 8 }}
            label={previewChip}
            color={devices.cameraStream || obsDevice ? "success" : "default"}
            variant="outlined"
          />
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25, minWidth: 0 }}>
          <Meter
            label="Mic level"
            value={devices.micLive ? devices.micDb : null}
            emptyLabel="no device"
            min={-60}
            max={0}
            unit=" dBFS"
          />
          <Box
            role="list"
            aria-label="Recording tracks"
            sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}
          >
            {rows.map((track) => (
              <Box role="listitem" key={track.id} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }} noWrap>
                  {track.label}
                </Typography>
                <StatusPill status={track.status} label={track.pill} detail={track.detail} />
              </Box>
            ))}
          </Box>
          <Typography variant="caption" color="text.disabled">
            {obsConnected
              ? obsRecording
                ? "OBS StartRecord is running"
                : "REC calls OBS StartRecord"
              : "OBS not running"}
          </Typography>
        </Box>
      </Box>
    </Panel>
  );
}
