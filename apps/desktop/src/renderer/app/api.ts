/**
 * REST access through RTK Query only (Section 9.1). Responses are validated with the zod schemas
 * generated from the Python protocol models (`@titan/protocol`).
 */
import {
  createApi,
  fetchBaseQuery,
  type BaseQueryFn,
  type FetchArgs,
  type FetchBaseQueryError,
} from "@reduxjs/toolkit/query/react";
import { SafetyStateSchema, SystemStatusSchema, type SafetyState, type SystemStatus } from "@titan/protocol";
import { z } from "zod";

import type { KillSwitchEvent } from "../../shared/ipc";
import { getTitan } from "./runtime";

export const API_PREFIX = "/api/v1";

export const HealthSchema = z.object({ status: z.literal("ok") });
export type Health = z.infer<typeof HealthSchema>;
export type { SystemStatus };

const baseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = (args, api, extra) => {
  const { apiBase, token } = getTitan();
  return fetchBaseQuery({
    baseUrl: `${apiBase}${API_PREFIX}`,
    timeout: 2500,
    prepareHeaders: (headers) => {
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return headers;
    },
  })(args, api, extra);
};

export const titanApi = createApi({
  reducerPath: "titanApi",
  baseQuery,
  endpoints: (build) => ({
    getHealth: build.query<Health, undefined>({
      query: () => "/health",
      transformResponse: (raw: unknown) => HealthSchema.parse(raw),
    }),
    getSystemStatus: build.query<SystemStatus, undefined>({
      query: () => "/system/status",
      transformResponse: (raw: unknown) => SystemStatusSchema.parse(raw),
    }),
    kill: build.mutation<SafetyState, KillSwitchEvent["source"]>({
      query: (source) => ({ url: "/safety/kill", method: "POST", body: { source } }),
      transformResponse: (raw: unknown) => SafetyStateSchema.parse(raw),
    }),
    resume: build.mutation<SafetyState, undefined>({
      query: () => ({ url: "/safety/resume", method: "POST", body: { confirm: "RESUME" } }),
      transformResponse: (raw: unknown) => SafetyStateSchema.parse(raw),
    }),
  }),
});

export const { useGetHealthQuery, useGetSystemStatusQuery, useKillMutation, useResumeMutation } = titanApi;
