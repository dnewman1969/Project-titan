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
    game_profile_id: z.string().uuid().optional(),
    title: z.string(),
    mode: z.enum(["observe", "replay", "autonomous"]),
    settings: z.record(z.unknown()).optional(),
  })
  .strict();
export type CreateSessionRequest = z.infer<typeof CreateSessionSchema>;

export const SessionCreatedSchema = z
  .object({
    id: z.string().uuid(),
    title: z.union([z.string(), z.null()]).optional(),
    state: z.string().optional(),
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

export const GameProfileListSchema = z
  .object({
    id: z.string().uuid(),
    install_path: z.string(),
    executable_path: z.string(),
    is_default: z.boolean().optional(),
    store: z.string().optional(),
  })
  .passthrough();

export const GameListItemSchema = z
  .object({
    id: z.string().uuid(),
    slug: z.string(),
    name: z.string(),
    research_status: z.string().optional(),
    profiles: z.array(GameProfileListSchema).optional(),
  })
  .passthrough();
export type GameListItem = z.infer<typeof GameListItemSchema>;

export const BlackboardEntrySchema = z
  .object({
    section: z.string(),
    key: z.string(),
    value: z.unknown(),
    author: z.string().optional(),
  })
  .passthrough();

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
    startSession: build.mutation<SessionCreated, { sessionId: string; launch_game?: boolean }>({
      query: ({ sessionId, launch_game = false }) => ({
        url: `/sessions/${sessionId}/start`,
        method: "POST",
        body: { launch_game },
      }),
      transformResponse: (raw: unknown) => SessionCreatedSchema.parse(raw),
    }),
    stopSession: build.mutation<SessionCreated, { sessionId: string; outcome?: string }>({
      query: ({ sessionId, outcome }) => ({
        url: `/sessions/${sessionId}/stop`,
        method: "POST",
        body: { outcome: outcome ?? "aborted" },
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
    listGames: build.query<{ items: GameListItem[] }, undefined>({
      query: () => "/games?include_profiles=true",
      transformResponse: (raw: unknown) => z.object({ items: z.array(GameListItemSchema) }).parse(raw),
    }),
    scanGames: build.mutation<
      { detected: Array<{ game_slug: string; install_path: string; profile_id: string }> },
      { extra_paths?: string[] } | undefined
    >({
      query: (body) => ({
        url: "/games/scan",
        method: "POST",
        body: { stores: ["steam", "epic", "gog"], extra_paths: body?.extra_paths ?? [] },
      }),
    }),
    createGameProfile: build.mutation<
      { id: string; install_path: string; executable_path: string },
      { game_slug: string; executable_path: string }
    >({
      query: (body) => ({ url: "/game-profiles", method: "POST", body }),
    }),
    getBlackboard: build.query<
      { bb_version: number; entries: Array<z.infer<typeof BlackboardEntrySchema>> },
      { sessionId: string; sinceVersion?: number }
    >({
      query: ({ sessionId, sinceVersion }) =>
        sinceVersion != null
          ? `/sessions/${sessionId}/blackboard?since_version=${sinceVersion}`
          : `/sessions/${sessionId}/blackboard`,
      transformResponse: (raw: unknown) =>
        z
          .object({
            bb_version: z.number(),
            entries: z.array(BlackboardEntrySchema),
          })
          .parse(raw),
    }),
    getPlayReadiness: build.query<
      {
        play_attach: {
          source: string;
          backend: string;
          ready: boolean;
          message: string;
          detail?: Record<string, unknown>;
        };
      },
      { gameSlug: string; source: "live" | "fixture" }
    >({
      query: ({ gameSlug, source }) => `/play/readiness?game_slug=${encodeURIComponent(gameSlug)}&source=${source}`,
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
  useStopSessionMutation,
  useGetActiveRecordingQuery,
  useStartRecordingMutation,
  useStopRecordingMutation,
  useListGamesQuery,
  useScanGamesMutation,
  useCreateGameProfileMutation,
  useGetBlackboardQuery,
  useGetPlayReadinessQuery,
  useKillMutation,
  useResumeMutation,
} = titanApi;
