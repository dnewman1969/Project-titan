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
import { SettingsDocumentSchema, type SettingsDocument } from "./settings";
import { getTitan } from "./runtime";

export const API_PREFIX = "/api/v1";

export const HealthSchema = z.object({ status: z.literal("ok") });
export type Health = z.infer<typeof HealthSchema>;
export type { SystemStatus, SettingsDocument };

/** Minimal create-session body for the New Session dialog (Section 5.2). */
export const CreateSessionSchema = z
  .object({
    game_slug: z.string(),
    title: z.string(),
    mode: z.enum(["observe", "replay", "autonomous"]),
    settings: z.record(z.unknown()).optional(),
  })
  .strict();
export type CreateSessionRequest = z.infer<typeof CreateSessionSchema>;

export const SessionCreatedSchema = z
  .object({
    id: z.string().uuid(),
    title: z.string(),
    state: z.string(),
  })
  .passthrough();
export type SessionCreated = z.infer<typeof SessionCreatedSchema>;

export const RecordingSchema = z
  .object({
    id: z.string().uuid(),
    session_id: z.string().uuid(),
    state: z.string(),
    manifest_path: z.string().nullable().optional(),
    root_dir: z.string().optional(),
    duration_ms: z.number().nullable().optional(),
  })
  .passthrough();
export type Recording = z.infer<typeof RecordingSchema>;

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
    getSettings: build.query<SettingsDocument, undefined>({
      query: () => "/settings",
      transformResponse: (raw: unknown) => SettingsDocumentSchema.parse(raw),
    }),
    patchSettings: build.mutation<SettingsDocument, { version: number; patch: Record<string, unknown> }>({
      query: ({ version, patch }) => ({
        url: "/settings",
        method: "PATCH",
        body: patch,
        headers: { "If-Match": String(version) },
      }),
      transformResponse: (raw: unknown) => SettingsDocumentSchema.parse(raw),
    }),
    createSession: build.mutation<SessionCreated, CreateSessionRequest>({
      query: (body) => ({ url: "/sessions", method: "POST", body }),
      transformResponse: (raw: unknown) => SessionCreatedSchema.parse(raw),
    }),
    startSession: build.mutation<SessionCreated, string>({
      query: (sessionId) => ({
        url: `/sessions/${sessionId}/start`,
        method: "POST",
        body: { launch_game: false },
      }),
      transformResponse: (raw: unknown) => SessionCreatedSchema.parse(raw),
    }),
    getActiveRecording: build.query<{ item: Recording | null }, string>({
      query: (sessionId) => `/sessions/${sessionId}/recordings/active`,
      transformResponse: (raw: unknown) => {
        const parsed = z.object({ item: RecordingSchema.nullable() }).parse(raw);
        return parsed;
      },
    }),
    startRecording: build.mutation<Recording, string>({
      query: (sessionId) => ({
        url: `/sessions/${sessionId}/recordings/start`,
        method: "POST",
      }),
      transformResponse: (raw: unknown) => RecordingSchema.parse(raw),
    }),
    stopRecording: build.mutation<Recording, string>({
      query: (sessionId) => ({
        url: `/sessions/${sessionId}/recordings/stop`,
        method: "POST",
      }),
      transformResponse: (raw: unknown) => RecordingSchema.parse(raw),
    }),
  }),
});

export const {
  useGetHealthQuery,
  useGetSystemStatusQuery,
  useGetSettingsQuery,
  usePatchSettingsMutation,
  useCreateSessionMutation,
  useStartSessionMutation,
  useGetActiveRecordingQuery,
  useStartRecordingMutation,
  useStopRecordingMutation,
  useKillMutation,
  useResumeMutation,
} = titanApi;
