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

export const CaptureTrackSchema = z
  .object({
    id: z.string(),
    kind: z.string().optional(),
    label: z.string().optional(),
    source: z.string().optional(),
    state: z.string().optional(),
    path: z.string().optional(),
  })
  .passthrough();
export type CaptureTrack = z.infer<typeof CaptureTrackSchema>;

export const RecordingSchema = z
  .object({
    id: z.string().uuid(),
    session_id: z.string().uuid(),
    state: z.string(),
    manifest_path: z.string().nullable().optional(),
    root_dir: z.string().optional(),
    duration_ms: z.number().nullable().optional(),
    error: z.string().nullable().optional(),
    tracks: z.array(CaptureTrackSchema).optional(),
    obs: z
      .object({
        connected: z.boolean().optional(),
        status: z.record(z.string(), z.unknown()).optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();
export type Recording = z.infer<typeof RecordingSchema>;

export const ObsCaptureStatusSchema = z
  .object({
    state: z.string(),
    detail: z.string().nullable().optional(),
    host: z.string().optional(),
    port: z.number().optional(),
    connected: z.boolean(),
    version: z.record(z.string(), z.unknown()).nullable().optional(),
    provision: z.record(z.string(), z.unknown()).nullable().optional(),
    record: z
      .object({
        active: z.boolean(),
        paused: z.boolean(),
        duration_ms: z.number().nullable().optional(),
      })
      .optional(),
  })
  .passthrough();
export type ObsCaptureStatus = z.infer<typeof ObsCaptureStatusSchema>;

export const YoutubeAccountSchema = z
  .object({
    id: z.string().uuid(),
    platform: z.string(),
    display_name: z.string(),
    remote_channel_id: z.string(),
    credential_ref: z.string(),
    status: z.string(),
    scopes: z.array(z.string()).optional(),
    connected_at: z.string().nullable().optional(),
    stub: z.boolean().optional(),
  })
  .passthrough();
export type YoutubeAccount = z.infer<typeof YoutubeAccountSchema>;

export const YoutubeAccountStatusSchema = z
  .object({
    connected: z.boolean(),
    stub: z.boolean().optional(),
    account: YoutubeAccountSchema.nullable(),
    message: z.string().optional(),
  })
  .passthrough();
export type YoutubeAccountStatus = z.infer<typeof YoutubeAccountStatusSchema>;

export const UploadJobSchema = z
  .object({
    id: z.string().uuid(),
    video_project_id: z.string().uuid(),
    account_id: z.string().uuid(),
    platform: z.string(),
    status: z.string(),
    privacy: z.string(),
    metadata: z.record(z.string(), z.unknown()).optional(),
    approved_at: z.string().nullable().optional(),
    approved_by: z.string().nullable().optional(),
    remote_video_id: z.string().nullable().optional(),
    remote_url: z.string().nullable().optional(),
    title: z.string().optional(),
    session_id: z.string().uuid().nullable().optional(),
  })
  .passthrough();
export type UploadJob = z.infer<typeof UploadJobSchema>;

export const TimelineEventSchema = z.record(z.string(), z.unknown());
export type TimelineEvent = z.infer<typeof TimelineEventSchema>;

export const RecordingTimelineSchema = z
  .object({
    session_id: z.string().uuid(),
    recording: RecordingSchema.nullable(),
    root_dir: z.string(),
    events: z.array(TimelineEventSchema),
  })
  .passthrough();
export type RecordingTimeline = z.infer<typeof RecordingTimelineSchema>;

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
    setSessionPlay: build.mutation<SessionCreated, { sessionId: string; enabled: boolean }>({
      query: ({ sessionId, enabled }) => ({
        url: `/sessions/${sessionId}/play`,
        method: "POST",
        body: { enabled },
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
    getRecordingTimeline: build.query<RecordingTimeline, { sessionId: string; limit?: number }>({
      query: ({ sessionId, limit }) =>
        `/sessions/${sessionId}/recordings/timeline${limit != null ? `?limit=${limit}` : ""}`,
      transformResponse: (raw: unknown) => RecordingTimelineSchema.parse(raw),
    }),
    getObsCaptureStatus: build.query<ObsCaptureStatus, undefined>({
      query: () => "/capture/obs",
      transformResponse: (raw: unknown) => ObsCaptureStatusSchema.parse(raw),
    }),
    getYoutubeAccount: build.query<YoutubeAccountStatus, undefined>({
      query: () => "/accounts/youtube",
      transformResponse: (raw: unknown) => YoutubeAccountStatusSchema.parse(raw),
    }),
    connectYoutubeStub: build.mutation<YoutubeAccountStatus, undefined>({
      query: () => ({ url: "/accounts/youtube/connect", method: "POST" }),
      transformResponse: (raw: unknown) => YoutubeAccountStatusSchema.parse(raw),
    }),
    disconnectYoutubeStub: build.mutation<YoutubeAccountStatus, undefined>({
      query: () => ({ url: "/accounts/youtube/disconnect", method: "POST" }),
      transformResponse: (raw: unknown) => YoutubeAccountStatusSchema.parse(raw),
    }),
    listUploadJobs: build.query<{ items: UploadJob[] }, { limit?: number } | undefined>({
      query: (args) => `/upload-jobs${args?.limit != null ? `?limit=${args.limit}` : ""}`,
      transformResponse: (raw: unknown) => z.object({ items: z.array(UploadJobSchema) }).parse(raw),
    }),
    createUploadJob: build.mutation<
      UploadJob,
      { title: string; session_id?: string; privacy?: "private" | "unlisted" | "public" }
    >({
      query: (body) => ({ url: "/upload-jobs", method: "POST", body }),
      transformResponse: (raw: unknown) => UploadJobSchema.parse(raw),
    }),
    approveUploadJob: build.mutation<UploadJob, string>({
      query: (jobId) => ({ url: `/upload-jobs/${jobId}/approve`, method: "POST" }),
      transformResponse: (raw: unknown) => UploadJobSchema.parse(raw),
    }),
    stubUploadJob: build.mutation<UploadJob, string>({
      query: (jobId) => ({ url: `/upload-jobs/${jobId}/upload`, method: "POST" }),
      transformResponse: (raw: unknown) => UploadJobSchema.parse(raw),
    }),
    listGames: build.query<{ items: GameListItem[] }, undefined>({
      query: () => "/games?include_profiles=true",
      transformResponse: (raw: unknown) => z.object({ items: z.array(GameListItemSchema) }).parse(raw),
    }),
    scanGames: build.mutation<
      {
        detected: Array<{ game_slug: string; install_path: string; profile_id: string }>;
        scan_context?: {
          steam_libraries?: string[];
          extra_paths?: string[];
          stores_scanned?: string[];
        };
      },
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
    memoryStatus: build.query<{ chroma: { state: string; version?: string; detail?: string } }, undefined>({
      query: () => "/memory/status",
    }),
    browseMemory: build.query<
      { items: Array<{ id: string; document?: string; metadata?: Record<string, unknown> }>; degraded: boolean },
      { gameSlug?: string; limit?: number }
    >({
      query: ({ gameSlug, limit }) => {
        const params = new URLSearchParams();
        if (gameSlug) params.set("game_slug", gameSlug);
        if (limit != null) params.set("limit", String(limit));
        const qs = params.toString();
        return `/memory/browse${qs ? `?${qs}` : ""}`;
      },
    }),
    searchMemory: build.query<
      { items: Array<{ id: string; document?: string; metadata?: Record<string, unknown>; distance?: number }> },
      { query: string; gameSlug?: string; n_results?: number }
    >({
      query: (body) => ({
        url: "/memory/search",
        method: "POST",
        body: {
          query: body.query,
          n_results: body.n_results ?? 12,
          ...(body.gameSlug ? { game_slug: body.gameSlug } : {}),
        },
      }),
    }),
    writeMemoryItem: build.mutation<
      { id: string; written: boolean },
      { document: string; game_slug: string; kind?: string; session_id?: string }
    >({
      query: (body) => ({ url: "/memory/items", method: "POST", body }),
    }),
    deleteMemoryItems: build.mutation<{ deleted: number }, { ids: string[] }>({
      query: (body) => ({ url: "/memory/delete", method: "POST", body }),
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
      query: ({ gameSlug, source }) =>
        `/play/readiness?game_slug=${encodeURIComponent(gameSlug)}&source=${source}`,
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
  useSetSessionPlayMutation,
  useGetActiveRecordingQuery,
  useGetRecordingTimelineQuery,
  useGetObsCaptureStatusQuery,
  useGetYoutubeAccountQuery,
  useConnectYoutubeStubMutation,
  useDisconnectYoutubeStubMutation,
  useListUploadJobsQuery,
  useCreateUploadJobMutation,
  useApproveUploadJobMutation,
  useStubUploadJobMutation,
  useStartRecordingMutation,
  useStopRecordingMutation,
  useListGamesQuery,
  useScanGamesMutation,
  useCreateGameProfileMutation,
  useGetBlackboardQuery,
  useMemoryStatusQuery,
  useBrowseMemoryQuery,
  useLazyBrowseMemoryQuery,
  useLazySearchMemoryQuery,
  useWriteMemoryItemMutation,
  useDeleteMemoryItemsMutation,
  useGetPlayReadinessQuery,
  useLazyGetPlayReadinessQuery,
  useKillMutation,
  useResumeMutation,
} = titanApi;
