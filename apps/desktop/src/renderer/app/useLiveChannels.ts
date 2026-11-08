import { useEffect } from "react";

import { safetyStateReceived } from "../features/safety/safetySlice";
import { metricsReceived } from "../features/telemetry/systemSlice";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";
import { LiveConnection, wsUrl } from "./ws";

/** Live `system.metrics` (telemetry bar, M1.T6) and `system.safety` over the WS gateway. */
export function useLiveChannels(): void {
  const dispatch = useAppDispatch();
  useEffect(() => {
    const titan = getTitan();
    if (titan.backend === "none") return;
    const connection = new LiveConnection({
      url: wsUrl(titan.apiBase),
      token: titan.token,
      client: `desktop/${titan.versions.app}`,
      handlers: {
        onMetrics: (metrics) => dispatch(metricsReceived(metrics)),
        onSafety: (state) => dispatch(safetyStateReceived(state)),
        onConnection: () => undefined,
      },
    });
    connection.start();
    return () => {
      connection.stop();
    };
  }, [dispatch]);
}
