CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
-- Apply: CREATE TRIGGER trg_<table>_updated BEFORE UPDATE ON <table> FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===================== Games =====================
CREATE TABLE games (
  id               uuid PRIMARY KEY,
  slug             text NOT NULL UNIQUE,                 -- 'ksp', 'ets2', 'ats'
  name             text NOT NULL,
  adapter_id       text NOT NULL,                        -- entry point name in titan.games
  adapter_version  text NOT NULL,
  domain           text NOT NULL CHECK (domain IN ('space','ground_vehicle','aircraft','naval','strategy','other')),
  genres           text[] NOT NULL DEFAULT '{}',
  capabilities     jsonb NOT NULL DEFAULT '{}',          -- {"telemetry":true,"control":"none","anti_cheat":false}
  store_ids        jsonb NOT NULL DEFAULT '{}',          -- {"steam":[227300]}
  research_status  text NOT NULL DEFAULT 'none' CHECK (research_status IN ('none','queued','running','complete','stale','failed')),
  manifest         jsonb NOT NULL,                       -- snapshot of titan-game.yaml
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE game_profiles (                            -- one detected installation
  id                 uuid PRIMARY KEY,
  game_id            uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  store              text NOT NULL CHECK (store IN ('steam','epic','gog','ubisoft','ea','standalone')),
  install_path       text NOT NULL,
  executable_path    text NOT NULL,
  launch_uri         text,                               -- steam://rungameid/227300
  launch_args        text[] NOT NULL DEFAULT '{}',
  game_version       text,                               -- Steam buildid or file version
  config_paths       jsonb NOT NULL DEFAULT '[]',
  save_paths         jsonb NOT NULL DEFAULT '[]',
  mod_paths          jsonb NOT NULL DEFAULT '[]',
  telemetry_status   text NOT NULL DEFAULT 'unknown' CHECK (telemetry_status IN ('unknown','missing','installed','connected','incompatible')),
  telemetry_details  jsonb NOT NULL DEFAULT '{}',        -- {"plugin":"scs-sdk-plugin","version":"1.12.1"}
  is_default         boolean NOT NULL DEFAULT false,
  last_seen_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, install_path)
);
CREATE UNIQUE INDEX ux_game_profiles_default ON game_profiles(game_id) WHERE is_default;

-- ===================== Agents =====================
CREATE TABLE agent_personas (
  id                      uuid PRIMARY KEY,
  slug                    text NOT NULL UNIQUE,          -- 'ksp.flight_engineer.gene'
  display_name            text NOT NULL,                 -- 'Gene'
  role                    text NOT NULL,                 -- 'flight_engineer'
  department              text NOT NULL CHECK (department IN ('director','research','agent_factory','training','gameplay','commentary','recording','video','seo','publish')),
  personality             jsonb NOT NULL,                -- {"traits":["dry","precise"],"humor":0.3,"verbosity":0.4,"catchphrases":[],"avoid":[]}
  backstory               text,
  speaking_style          text,
  system_prompt_template  text NOT NULL,                 -- Jinja2; vars: persona, game, mission, role_brief
  voice                   jsonb,                         -- (P5) {"engine":"xtts","voice_id":"...","rate":1.0}
  portrait_path           text,                          -- (P5) generated portrait
  color_hex               char(7) NOT NULL DEFAULT '#888888',
  model_role              text NOT NULL DEFAULT 'agent', -- key into models.yaml roles
  game_id                 uuid REFERENCES games(id) ON DELETE SET NULL, -- NULL = universal
  source                  text NOT NULL CHECK (source IN ('builtin','user','factory')),
  version                 int NOT NULL DEFAULT 1,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_teams (
  id             uuid PRIMARY KEY,
  game_id        uuid REFERENCES games(id) ON DELETE CASCADE,  -- NULL = universal team
  name           text NOT NULL,
  purpose        text NOT NULL,
  template_slug  text,                                 -- 'ksp.default'
  source         text NOT NULL CHECK (source IN ('builtin','user','factory')),
  version        int NOT NULL DEFAULT 1,
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, name, version)
);

CREATE TABLE agents (                                  -- durable agent definition (role within a team)
  id                 uuid PRIMARY KEY,
  team_id            uuid NOT NULL REFERENCES agent_teams(id) ON DELETE CASCADE,
  persona_id         uuid NOT NULL REFERENCES agent_personas(id),
  role               text NOT NULL,
  is_director        boolean NOT NULL DEFAULT false,
  responsibilities   text[] NOT NULL DEFAULT '{}',
  tools              text[] NOT NULL DEFAULT '{}',     -- allowlisted tool ids
  bb_read_sections   text[] NOT NULL DEFAULT '{goals,plan,world_state,facts,risks}',
  bb_write_sections  text[] NOT NULL DEFAULT '{facts,hypotheses,risks,discoveries}',
  event_subscriptions text[] NOT NULL DEFAULT '{}',    -- glob patterns: 'ksp.staging', 'scs.job.*'
  tick_interval_ms   int NOT NULL DEFAULT 10000 CHECK (tick_interval_ms >= 2000),
  can_commentate     boolean NOT NULL DEFAULT true,
  can_act            boolean NOT NULL DEFAULT false,   -- must be false in P1 (enforced by CHECK below in P1 migration)
  status             text NOT NULL DEFAULT 'active' CHECK (status IN ('active','probation','retired')),
  stats              jsonb NOT NULL DEFAULT '{}',      -- rolling: tasks_ok, tasks_failed, avg_eval, utterances
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_id, role),
  CONSTRAINT p1_no_actions CHECK (can_act = false)     -- dropped by the Phase 4 migration
);
CREATE UNIQUE INDEX ux_agents_one_director ON agents(team_id) WHERE is_director;

-- ===================== Sessions, missions, tasks =====================
CREATE TABLE sessions (
  id                    uuid PRIMARY KEY,
  game_id               uuid NOT NULL REFERENCES games(id),
  game_profile_id       uuid REFERENCES game_profiles(id) ON DELETE SET NULL,
  team_id               uuid REFERENCES agent_teams(id) ON DELETE SET NULL,
  title                 text,
  mode                  text NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe','assist','autonomous','replay')),
  state                 text NOT NULL DEFAULT 'created' CHECK (state IN ('created','starting','live','paused','stopping','ended','failed')),
  replay_of_session_id  uuid REFERENCES sessions(id),
  clock_origin_mono_ns  bigint,
  clock_origin_wall     timestamptz,
  started_at            timestamptz,
  ended_at              timestamptz,
  data_dir              text NOT NULL,
  game_version          text,
  settings              jsonb NOT NULL DEFAULT '{}',   -- recording preset, agent toggles, model profile
  outcome               text CHECK (outcome IN ('success','partial','failure','aborted')),
  summary               jsonb,                          -- end-of-session report (Sec 6.10)
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_sessions_game_started ON sessions(game_id, started_at DESC);
CREATE UNIQUE INDEX ux_sessions_one_live ON sessions((true)) WHERE state IN ('starting','live','paused','stopping') AND mode <> 'replay';

CREATE TABLE missions (
  id                 uuid PRIMARY KEY,
  session_id         uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  game_id            uuid NOT NULL REFERENCES games(id),
  parent_mission_id  uuid REFERENCES missions(id) ON DELETE CASCADE,
  title              text NOT NULL,
  objective          text NOT NULL,
  success_criteria   jsonb NOT NULL DEFAULT '[]',      -- predicates over telemetry (Sec 7.5 DSL)
  failure_criteria   jsonb NOT NULL DEFAULT '[]',
  status             text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','succeeded','failed','abandoned')),
  priority           smallint NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
  created_by         text NOT NULL,                     -- 'user' | 'director' | 'agent:<instance_id>'
  started_at         timestamptz,
  ended_at           timestamptz,
  result             jsonb,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_missions_session ON missions(session_id, status);

CREATE TABLE agent_instances (                         -- runtime spawn of an agent within a session
  id                  uuid PRIMARY KEY,
  agent_id            uuid NOT NULL REFERENCES agents(id),
  session_id          uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  state               text NOT NULL CHECK (state IN ('spawning','ready','busy','paused','terminating','terminated','crashed')),
  spawned_by          text NOT NULL,                    -- 'session_start' | 'director' | 'user'
  spawned_at          timestamptz NOT NULL DEFAULT now(),
  terminated_at       timestamptz,
  termination_reason  text,
  model_resolved      text,                             -- 'ollama:qwen3:8b'
  lg_thread_id        text NOT NULL,
  tokens_in           bigint NOT NULL DEFAULT 0,
  tokens_out          bigint NOT NULL DEFAULT 0,
  messages_sent       int NOT NULL DEFAULT 0,
  last_heartbeat_at   timestamptz
);
CREATE INDEX ix_agent_instances_session ON agent_instances(session_id, state);

CREATE TABLE tasks (                                   -- Director-managed work items (Sec 6.5)
  id                     uuid PRIMARY KEY,
  session_id             uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  mission_id             uuid REFERENCES missions(id) ON DELETE SET NULL,
  parent_task_id         uuid REFERENCES tasks(id) ON DELETE CASCADE,
  kind                   text NOT NULL,                 -- 'analyze','plan','monitor','explain','compute','summarize'
  title                  text NOT NULL,
  input                  jsonb NOT NULL DEFAULT '{}',
  output                 jsonb,
  assignee_role          text,
  assignee_instance_id   uuid REFERENCES agent_instances(id) ON DELETE SET NULL,
  state                  text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','assigned','accepted','in_progress','blocked','completed','failed','cancelled','timed_out')),
  priority               smallint NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
  attempts               smallint NOT NULL DEFAULT 0,
  max_attempts           smallint NOT NULL DEFAULT 2,
  deadline_at            timestamptz,
  assigned_at            timestamptz,
  accepted_at            timestamptz,
  completed_at           timestamptz,
  failure_reason         text,
  evaluation             jsonb,                         -- {"score":0.0-1.0,"notes":"...","by":"director"}
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_tasks_session_state ON tasks(session_id, state);
CREATE INDEX ix_tasks_assignee ON tasks(assignee_instance_id) WHERE state IN ('assigned','accepted','in_progress','blocked');

-- ===================== Knowledge, strategy, risk, controls =====================
CREATE TABLE research_sources (                        -- (P2, created in P1)
  id            uuid PRIMARY KEY,
  game_id       uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('official_docs','wiki','forum','reddit','steam_guide','patch_notes','video','dev_blog','mod_docs','local_file','user')),
  url           text,
  local_path    text,
  title         text,
  fetched_at    timestamptz,
  http_status   int,
  content_hash  char(64),
  robots_allowed boolean,
  license_note  text,
  raw_path      text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, url)
);

CREATE TABLE knowledge_entries (
  id            uuid PRIMARY KEY,
  game_id       uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('mechanic','objective','economy','combat','progression','tech_tree','crafting','exploration','control','ui','vehicle','location','glossary','other')),
  title         text NOT NULL,
  body          text NOT NULL,
  structured    jsonb NOT NULL DEFAULT '{}',
  source_id     uuid REFERENCES research_sources(id) ON DELETE SET NULL,
  game_version  text,
  confidence    real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  verified      boolean NOT NULL DEFAULT false,
  content_hash  char(64) NOT NULL,
  chroma_id     text,                                    -- = id::text in collection 'knowledge'
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, content_hash)
);
CREATE INDEX ix_knowledge_tsv ON knowledge_entries USING gin(tsv);
CREATE INDEX ix_knowledge_game_kind ON knowledge_entries(game_id, kind);

CREATE TABLE strategies (
  id                  uuid PRIMARY KEY,
  game_id             uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  title               text NOT NULL,
  level               text NOT NULL CHECK (level IN ('beginner','advanced','endgame','common_mistake','workflow')),
  situation           text NOT NULL,                     -- when it applies
  steps               jsonb NOT NULL DEFAULT '[]',
  rationale           text,
  source_kind         text NOT NULL CHECK (source_kind IN ('research','learned','user','builtin')),
  source_refs         jsonb NOT NULL DEFAULT '[]',       -- [{"type":"session","id":...},{"type":"source","id":...}]
  confidence          real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  times_used          int NOT NULL DEFAULT 0,
  times_succeeded     int NOT NULL DEFAULT 0,
  status              text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','active','deprecated')),
  superseded_by       uuid REFERENCES strategies(id),
  game_version_range  text,
  chroma_id           text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_strategies_game_status ON strategies(game_id, status, level);

CREATE TABLE risk_entries (
  id                  uuid PRIMARY KEY,
  game_id             uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  title               text NOT NULL,                     -- 'Fuel starvation during ascent'
  description         text NOT NULL,
  category            text NOT NULL CHECK (category IN ('crash','overheat','fuel','structural','economy','traffic_law','fatigue','mission_fail','other')),
  trigger_conditions  jsonb NOT NULL DEFAULT '[]',       -- predicate DSL (Sec 7.5)
  severity            smallint NOT NULL CHECK (severity BETWEEN 1 AND 5),
  likelihood          smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  mitigation          text,
  event_type          text,                              -- event emitted when trigger fires
  source_kind         text NOT NULL CHECK (source_kind IN ('research','learned','user','builtin')),
  source_refs         jsonb NOT NULL DEFAULT '[]',
  occurrences         int NOT NULL DEFAULT 0,
  last_occurred_at    timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_risks_game ON risk_entries(game_id, category);

CREATE TABLE control_bindings (
  id               uuid PRIMARY KEY,
  game_id          uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  game_profile_id  uuid REFERENCES game_profiles(id) ON DELETE CASCADE,   -- NULL = game default
  action_id        text NOT NULL,                      -- canonical: 'ksp.stage', 'vehicle.throttle'
  action_label     text NOT NULL,
  context          text NOT NULL DEFAULT 'default',    -- 'flight','map','eva','driving','menu'
  device           text NOT NULL CHECK (device IN ('keyboard','mouse','gamepad','joystick','hotas','wheel','api')),
  binding          jsonb NOT NULL,                      -- {"key":"Space","mods":[]} | {"axis":"LT","invert":false}
  action_class     text NOT NULL CHECK (action_class IN ('continuous','discrete','irreversible','menu')),
  source           text NOT NULL CHECK (source IN ('default','config_file','research','user')),
  confidence       real NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (game_id, game_profile_id, action_id, context, device)
);

-- ===================== Memory =====================
CREATE TABLE memories (
  id                uuid PRIMARY KEY,
  game_id           uuid REFERENCES games(id) ON DELETE CASCADE,
  agent_id          uuid REFERENCES agents(id) ON DELETE SET NULL,       -- NULL = team/shared memory
  session_id        uuid REFERENCES sessions(id) ON DELETE SET NULL,
  mission_id        uuid REFERENCES missions(id) ON DELETE SET NULL,
  tier              text NOT NULL CHECK (tier IN ('short_term','long_term','episodic','strategic','failure')),
  kind              text NOT NULL CHECK (kind IN ('observation','discovery','lesson','success','failure','summary','reflection','callback')),
  content           text NOT NULL,                     -- natural-language memory (<= 1000 chars)
  structured        jsonb NOT NULL DEFAULT '{}',
  importance        real NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
  confidence        real NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
  t_session_ms      bigint,
  occurred_at       timestamptz NOT NULL DEFAULT now(),
  access_count      int NOT NULL DEFAULT 0,
  last_accessed_at  timestamptz,
  expires_at        timestamptz,                       -- short_term: session end + 24h
  supersedes        uuid REFERENCES memories(id),
  chroma_id         text,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_memories_game_tier ON memories(game_id, tier, importance DESC);
CREATE INDEX ix_memories_session ON memories(session_id);
CREATE INDEX ix_memories_expiry ON memories(expires_at) WHERE expires_at IS NOT NULL;

-- ===================== Blackboard, events, messages, telemetry =====================
CREATE TABLE blackboard_entries (                       -- append-only history; current = max(version) per key
  id           uuid PRIMARY KEY,
  session_id   uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  section      text NOT NULL CHECK (section IN ('goals','plan','tasks','world_state','facts','hypotheses','risks','discoveries','lessons','notes')),
  key          text NOT NULL CHECK (key ~ '^[a-z0-9_.:-]{1,128}$'),
  version      int NOT NULL CHECK (version >= 1),
  op           text NOT NULL CHECK (op IN ('put','retract')),
  value        jsonb,
  author       text NOT NULL,                          -- 'agent:<instance_id>' | 'director' | 'system' | 'user'
  confidence   real CHECK (confidence BETWEEN 0 AND 1),
  evidence     jsonb NOT NULL DEFAULT '[]',            -- [{"type":"event","id":...},{"type":"telemetry","t_session_ms":...}]
  message_id   uuid,                                    -- envelope that caused this write
  bb_version   bigint NOT NULL,                         -- global blackboard counter at write
  expires_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, section, key, version)
);
CREATE INDEX ix_bb_session_version ON blackboard_entries(session_id, bb_version);
CREATE VIEW blackboard_current AS
  SELECT DISTINCT ON (session_id, section, key) *
  FROM blackboard_entries
  ORDER BY session_id, section, key, version DESC;

CREATE TABLE events (
  id            uuid PRIMARY KEY,
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq           bigint NOT NULL,                        -- per-session monotonically increasing
  type          text NOT NULL,                          -- 'ksp.staging', 'scs.job.delivered', 'recording.started'
  category      text NOT NULL CHECK (category IN ('game','agent','system','user','safety','recording')),
  severity      text NOT NULL CHECK (severity IN ('debug','info','notice','warning','critical')),
  salience      real NOT NULL DEFAULT 0.3 CHECK (salience BETWEEN 0 AND 1),
  source        text NOT NULL,                          -- 'adapter:ksp', 'rule:ksp.max_q', 'capture'
  t_mono_ns     bigint NOT NULL,
  t_session_ms  bigint NOT NULL,
  occurred_at   timestamptz NOT NULL,
  payload       jsonb NOT NULL DEFAULT '{}',
  frame_seq     bigint,                                 -- telemetry frame that triggered it
  UNIQUE (session_id, seq)
);
CREATE INDEX ix_events_session_time ON events(session_id, t_session_ms);
CREATE INDEX ix_events_session_type ON events(session_id, type);

CREATE TABLE agent_messages (                          -- persisted bus envelopes
  id              uuid PRIMARY KEY,                     -- = envelope.id
  session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  stream_seq      text NOT NULL,                        -- Redis stream id
  type            text NOT NULL,
  sender          text NOT NULL,
  recipients      text[] NOT NULL,
  correlation_id  uuid,
  causation_id    uuid,
  visibility      text NOT NULL CHECK (visibility IN ('public','internal')),
  payload         jsonb NOT NULL,
  t_session_ms    bigint NOT NULL,
  created_at      timestamptz NOT NULL
);
CREATE INDEX ix_msgs_session_time ON agent_messages(session_id, t_session_ms);
CREATE INDEX ix_msgs_correlation ON agent_messages(correlation_id);

CREATE TABLE telemetry_samples (                       -- 1 Hz downsample; raw frames in session files
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  t_session_ms  bigint NOT NULL,
  frame         jsonb NOT NULL,                         -- normalized TelemetryFrame
  PRIMARY KEY (session_id, t_session_ms)
);

CREATE TABLE llm_calls (
  id                 uuid PRIMARY KEY,
  session_id         uuid REFERENCES sessions(id) ON DELETE SET NULL,
  agent_instance_id  uuid REFERENCES agent_instances(id) ON DELETE SET NULL,
  provider           text NOT NULL,
  model              text NOT NULL,
  model_role         text NOT NULL,
  purpose            text NOT NULL,                     -- 'commentary','decide','director_plan','summary'
  priority           smallint NOT NULL,
  prompt_tokens      int NOT NULL DEFAULT 0,
  completion_tokens  int NOT NULL DEFAULT 0,
  ttft_ms            int,
  latency_ms         int,
  status             text NOT NULL CHECK (status IN ('ok','error','cancelled','timeout','dropped')),
  error              text,
  prompt_hash        char(64),
  prompt_path        text,                              -- only if logging.llm_prompts=true
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_calls_session ON llm_calls(session_id, created_at);

-- ===================== Recording =====================
CREATE TABLE recordings (
  id              uuid PRIMARY KEY,
  session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  state           text NOT NULL CHECK (state IN ('starting','recording','stopping','finalizing','complete','error')),
  preset          jsonb NOT NULL,                       -- {"width":1920,"height":1080,"fps":60,"encoder":"jim_nvenc","cq":20}
  start_mono_ns   bigint,
  started_at      timestamptz,
  stopped_at      timestamptz,
  duration_ms     bigint,
  root_dir        text NOT NULL,
  manifest_path   text,
  total_bytes     bigint NOT NULL DEFAULT 0,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recordings_session ON recordings(session_id);

CREATE TABLE recording_tracks (
  id               uuid PRIMARY KEY,
  recording_id     uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  track_no         smallint NOT NULL,                   -- editor track number (Sec 2.12, P6 tracks 1-8)
  kind             text NOT NULL CHECK (kind IN ('gameplay_video','webcam_video','game_audio','mic_audio','agent_voice','user_commentary','music','system_audio','effects','overlay','captions','telemetry','events')),
  file_path        text NOT NULL,
  container        text,
  codec            text,
  width            int, height int, fps numeric(6,3),
  sample_rate      int, channels smallint,
  start_offset_ms  int NOT NULL DEFAULT 0,              -- relative to recordings.start_mono_ns
  duration_ms      bigint,
  bytes            bigint,
  sha256           char(64),
  dropped_frames   int NOT NULL DEFAULT 0,
  state            text NOT NULL CHECK (state IN ('recording','finalized','corrupt','missing')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (recording_id, kind, track_no)
);

CREATE TABLE markers (                                 -- highlight candidates and user markers
  id            uuid PRIMARY KEY,
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  recording_id  uuid REFERENCES recordings(id) ON DELETE CASCADE,
  event_id      uuid REFERENCES events(id) ON DELETE SET NULL,
  t_ms          bigint NOT NULL,                        -- recording timeline ms
  duration_ms   int NOT NULL DEFAULT 0,
  kind          text NOT NULL CHECK (kind IN ('highlight','achievement','failure','funny','tension','emotional','mission_complete','chapter','user')),
  score         real NOT NULL DEFAULT 0.5 CHECK (score BETWEEN 0 AND 1),
  label         text,
  created_by    text NOT NULL,                          -- 'rule','agent:<id>','user','highlight_model'
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_markers_recording ON markers(recording_id, t_ms);

-- ===================== Video, thumbnails, publishing, analytics (P6-P8; created in P1) =====================
CREATE TABLE video_projects (
  id                uuid PRIMARY KEY,
  session_id        uuid REFERENCES sessions(id) ON DELETE SET NULL,
  title             text NOT NULL,
  status            text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','rough_cut','editing','rendering','rendered','published','archived','failed')),
  timeline_path     text,                               -- OpenTimelineIO .otio
  timeline_version  int NOT NULL DEFAULT 0,
  render_profile    jsonb NOT NULL DEFAULT '{}',
  output_path       text,
  duration_ms       bigint,
  chapters          jsonb NOT NULL DEFAULT '[]',        -- [{"t_ms":0,"title":"Intro"}]
  captions_path     text,
  seo               jsonb NOT NULL DEFAULT '{}',        -- {"title","description","tags":[],"hashtags":[],"pinned_comment"}
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE video_project_sources (
  video_project_id  uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  recording_id      uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  PRIMARY KEY (video_project_id, recording_id)
);

CREATE TABLE thumbnails (
  id                uuid PRIMARY KEY,
  video_project_id  uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  style             text NOT NULL CHECK (style IN ('mrbeast','documentary','gaming','educational','simulation','humorous','professional')),
  source_marker_id  uuid REFERENCES markers(id) ON DELETE SET NULL,
  prompt            text,
  generator         jsonb NOT NULL DEFAULT '{}',        -- {"engine":"comfyui","workflow":"...","model":"flux-dev","seed":123}
  image_path        text NOT NULL,
  width             int NOT NULL, height int NOT NULL,
  score             real,                               -- predicted appeal 0-1
  selected          boolean NOT NULL DEFAULT false,
  ctr               real,                               -- observed (P8)
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_thumbnails_selected ON thumbnails(video_project_id) WHERE selected;

CREATE TABLE platform_accounts (
  id                 uuid PRIMARY KEY,
  platform           text NOT NULL CHECK (platform IN ('youtube','twitch','tiktok','kick','x','facebook')),
  display_name       text NOT NULL,
  remote_channel_id  text NOT NULL,
  scopes             text[] NOT NULL DEFAULT '{}',
  credential_ref     text NOT NULL,                     -- keyring service/key; token never stored here
  status             text NOT NULL CHECK (status IN ('connected','expired','revoked')),
  connected_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (platform, remote_channel_id)
);

CREATE TABLE upload_jobs (
  id                    uuid PRIMARY KEY,
  video_project_id      uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  account_id            uuid NOT NULL REFERENCES platform_accounts(id),
  platform              text NOT NULL,
  status                text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','awaiting_approval','approved','uploading','processing','scheduled','published','failed','cancelled')),
  privacy               text NOT NULL DEFAULT 'private' CHECK (privacy IN ('private','unlisted','public')),
  scheduled_publish_at  timestamptz,
  metadata              jsonb NOT NULL,                 -- final title/description/tags/category/chapters/thumbnail_id
  approved_by           text,                           -- must be 'user'; API refuses otherwise
  approved_at           timestamptz,
  upload_session_uri    text,                           -- resumable upload URI
  bytes_sent            bigint NOT NULL DEFAULT 0,
  bytes_total           bigint,
  remote_video_id       text,
  remote_url            text,
  attempts              smallint NOT NULL DEFAULT 0,
  last_error            text,
  quota_units_used      int NOT NULL DEFAULT 0,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT approval_required CHECK (status NOT IN ('approved','uploading','processing','scheduled','published') OR approved_at IS NOT NULL)
);
CREATE INDEX ix_upload_jobs_status ON upload_jobs(status);

CREATE TABLE analytics_snapshots (
  id                  uuid PRIMARY KEY,
  upload_job_id       uuid NOT NULL REFERENCES upload_jobs(id) ON DELETE CASCADE,
  remote_video_id     text NOT NULL,
  captured_at         timestamptz NOT NULL,
  time_window         text NOT NULL CHECK (time_window IN ('1h','24h','7d','28d','lifetime')),
  views               bigint, impressions bigint,
  ctr                 numeric(6,4),
  watch_time_minutes  numeric(12,2),
  avg_view_duration_s numeric(10,2),
  avg_view_pct        numeric(6,3),
  likes int, comments int, shares int,
  subscribers_gained int, subscribers_lost int,
  retention_curve     jsonb,                            -- [[pct_of_video, audience_ratio], ...]
  raw                 jsonb NOT NULL DEFAULT '{}',
  UNIQUE (upload_job_id, time_window, captured_at)
);

CREATE TABLE settings (
  key         text PRIMARY KEY,                         -- 'ui.layout', 'safety.kill_hotkey'
  value       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
