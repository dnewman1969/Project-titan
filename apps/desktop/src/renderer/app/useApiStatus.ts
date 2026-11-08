import type { Status } from "@titan/ui-kit";
import { useEffect, useRef } from "react";

import { logEvent } from "../features/events/eventsSlice";
import { SERVICE_STATUS } from "../features/system/supervisorSlice";
import { useGetHealthQuery, useGetSystemStatusQuery, type SystemStatus } from "./api";
import { useAppDispatch } from "./hooks";

export const HEALTH_POLL_MS = 3000;
export const STATUS_POLL_MS = 5000;

export interface ApiStatus {
  api: Status;
  apiDetail: string;
  postgres: Status;
  postgresDetail: string;
  services: Status;
  servicesDetail: string;
}

const RANK: Status[] = ["ok", "unknown", "degraded", "down"];

/** One pill for every supervised process: the worst state wins. */
export function summarizeServices(services: SystemStatus["services"] | undefined): [Status, string] {
  if (!services?.length) return ["unknown", "no status yet"];
  let worst: Status = "ok";
  const problems: string[] = [];
  for (const service of services) {
    const status = SERVICE_STATUS[service.state];
    if (RANK.indexOf(status) > RANK.indexOf(worst)) worst = status;
    if (status !== "ok") problems.push(`${service.name} ${service.state}`);
  }
  return [worst, problems.length ? problems.join(", ") : `${services.length} running`];
}

export function useApiStatus(): ApiStatus {
  const dispatch = useAppDispatch();
  const health = useGetHealthQuery(undefined, { pollingInterval: HEALTH_POLL_MS });
  const healthy = health.isSuccess && !health.isError;
  const status = useGetSystemStatusQuery(undefined, { pollingInterval: STATUS_POLL_MS, skip: !healthy });

  let api: Status = "unknown";
  let apiDetail = "connecting";
  if (healthy && status.isError) {
    api = "degraded";
    apiDetail = "health ok, status request rejected (launch token?)";
  } else if (healthy) {
    api = "ok";
    apiDetail = "healthy";
  } else if (health.isError) {
    api = "down";
    apiDetail = "unreachable";
  }

  const pg = status.data?.dependencies.postgres;
  const postgres: Status = healthy && pg ? SERVICE_STATUS[pg.state] : "unknown";
  const [services, servicesDetail]: [Status, string] = healthy
    ? summarizeServices(status.data?.services)
    : ["unknown", "API offline"];
  const postgresDetail = pg?.detail ?? pg?.version ?? (healthy ? "checking" : "API offline");

  const previous = useRef<Status>("unknown");
  useEffect(() => {
    if (api === previous.current || api === "unknown") return;
    const was = previous.current;
    previous.current = api;
    if (api === "ok") {
      dispatch(
        logEvent({ type: "system.api_up", category: "system", severity: "info", text: "API connected" }),
      );
    } else if (api === "down" && was !== "unknown") {
      dispatch(
        logEvent({
          type: "system.api_down",
          category: "system",
          severity: "warning",
          text: "API unreachable",
        }),
      );
    } else if (api === "down") {
      dispatch(
        logEvent({
          type: "system.api_down",
          category: "system",
          severity: "notice",
          text: "API not reachable yet; start it with `uv run titan-api` or `pnpm dev`",
        }),
      );
    } else {
      dispatch(
        logEvent({ type: "system.api_degraded", category: "system", severity: "warning", text: apiDetail }),
      );
    }
  }, [api, apiDetail, dispatch]);

  return { api, apiDetail, postgres, postgresDetail, services, servicesDetail };
}
