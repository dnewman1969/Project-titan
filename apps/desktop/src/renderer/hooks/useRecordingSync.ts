import { useEffect } from "react";

import { useGetActiveRecordingQuery } from "../app/api";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { setRecordingActive, setRecordingRootDir } from "../features/sessions/sessionsSlice";

/** Keep REC button state aligned with the API active recording (double-click / record-on-start safe). */
export function useRecordingSync(): void {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const recordingActive = useAppSelector((s) => s.sessions.recordingActive);
  const recordingRootDir = useAppSelector((s) => s.sessions.recordingRootDir);
  const { data } = useGetActiveRecordingQuery(sessionId ?? "", {
    skip: !sessionId,
    pollingInterval: 4000,
  });

  useEffect(() => {
    if (!sessionId || data === undefined) return;
    const item = data.item;
    const active = item !== null && (item.state === "recording" || item.state === "starting" || item.state === "stopping");
    if (active !== recordingActive) {
      dispatch(setRecordingActive(active));
    }
    const root = typeof item?.root_dir === "string" ? item.root_dir : null;
    if (active && root && root !== recordingRootDir) {
      dispatch(setRecordingRootDir(root));
    }
    if (!active && recordingRootDir && item === null) {
      // Keep last root_dir so Record → Open Folder still works after stop.
    }
  }, [data, dispatch, recordingActive, recordingRootDir, sessionId]);
}
