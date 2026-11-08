/**
 * REST access through RTK Query only (Section 9.1). Responses are validated with zod; these
 * schemas mirror the API's OpenAPI models until a generated REST client replaces them.
 */
import {
  createApi,
  fetchBaseQuery,
  type BaseQueryFn,
  type FetchArgs,
  type FetchBaseQueryError,
} from "@reduxjs/toolkit/query/react";
import { z } from "zod";

import { getTitan } from "./runtime";

export const API_PREFIX = "/api/v1";

const ServiceStateName = z.enum(["up", "down", "starting", "degraded", "unknown"]);

export const HealthSchema = z.object({ status: z.literal("ok") });
export type Health = z.infer<typeof HealthSchema>;

export const SystemStatusSchema = z.object({
  services: z.array(
    z.object({
      name: z.string(),
      state: ServiceStateName,
      pid: z.number().int().nullable(),
      restarts: z.number().int(),
      since: z.string().nullable(),
    }),
  ),
  dependencies: z.record(
    z.object({ state: ServiceStateName, version: z.string().nullable(), detail: z.string().nullable() }),
  ),
  resource_guard_level: z.enum(["L0", "L1", "L2", "L3", "L4"]),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;

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
  }),
});

export const { useGetHealthQuery, useGetSystemStatusQuery } = titanApi;
