import { useEffect } from "react";

import { logEvent } from "../features/events/eventsSlice";
import { safetyStateReceived } from "../features/safety/safetySlice";
import { telemetryFrameReceived } from "../features/telemetry/gameTelemetrySlice";
import { metricsReceived } from "../features/telemetry/systemSlice";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";
import { LiveConnection, wsUrl } from "./ws";

/** Live system and session telemetry/events over the WS gateway (M1.T6, M5.T6). */
export function useLiveChannels(): void {
  const dispatch = useAppDispatch();
  useEffect(() => {
    const titan = getTitan();
    if (titan.backend === "none") return;
    const demoSession = import.meta.env.VITE_TITAN_DEMO_SESSION as string | undefined;
    const sessionChannels = demoSession
      ? [`session.${demoSession}.telemetry`, `session.${demoSession}.events`]
      : [];
    const connection = new LiveConnection({
      url: wsUrl(titan.apiBase),
      token: titan.token,
      client: `desktop/${titan.versions.app}`,
      sessionChannels,
      handlers: {
        onMetrics: (metrics) => dispatch(metricsReceived(metrics)),
        onSafety: (state) => dispatch(safetyStateReceived(state)),
        onTelemetryFrame: (frame) => dispatch(telemetryFrameReceived(frame)),
        onGameEvent: (event) =>
          dispatch(
            logEvent({
              type: event.type,
              category: event.category,
              severity: event.severity,
              text: event.type,
            }),
          ),
        onConnection: () => undefined,
      },
    });
    connection.start();
    return () => {
      connection.stop();
    };
  }, [dispatch]);
}
