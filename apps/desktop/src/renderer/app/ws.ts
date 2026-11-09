/**
 * WebSocket client for the API gateway (Section 5.3): auth first, then subscriptions, every frame
 * validated with the generated zod schemas, reconnect with backoff.
 */
import {
  GameEventSchema,
  SafetyStateSchema,
  ServerFrameSchema,
  SystemMetricsSchema,
  TelemetryFrameUISchema,
  WS_CLOSE_UNAUTHORIZED,
  type GameEvent,
  type SafetyState,
  type SystemMetrics,
  type TelemetryFrameUI,
} from "@titan/protocol";

export const AUTH_REQ_ID = "auth";
export const CHANNELS = ["system.metrics", "system.safety"] as const;
export const RECONNECT_MIN_MS = 1000;
export const RECONNECT_MAX_MS = 10_000;

export interface LiveHandlers {
  onMetrics(metrics: SystemMetrics): void;
  onSafety(state: SafetyState): void;
  onGameEvent?(event: GameEvent): void;
  onTelemetryFrame?(frame: TelemetryFrameUI): void;
  onConnection(connected: boolean, detail: string): void;
}

export interface LiveOptions {
  url: string;
  token: string;
  client: string;
  handlers: LiveHandlers;
  sessionChannels?: string[];
  WebSocketImpl?: typeof WebSocket;
}

export function wsUrl(apiBase: string): string {
  return `${apiBase.replace(/^http/, "ws")}/api/v1/ws`;
}

export class LiveConnection {
  private socket: WebSocket | null = null;
  private retryMs = RECONNECT_MIN_MS;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  private nextReq = 1;

  constructor(private readonly options: LiveOptions) {}

  start(): void {
    this.closed = false;
    this.connect();
  }

  stop(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.socket?.close(1000);
    this.socket = null;
  }

  private connect(): void {
    const Impl = this.options.WebSocketImpl ?? WebSocket;
    const socket = new Impl(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ op: "auth", token: this.options.token, client: this.options.client }));
    };
    socket.onmessage = (event: MessageEvent) => {
      this.receive(socket, typeof event.data === "string" ? event.data : "");
    };
    socket.onclose = (event: CloseEvent) => {
      if (this.socket !== socket) return;
      this.socket = null;
      const reason =
        event.code === WS_CLOSE_UNAUTHORIZED ? "launch token rejected" : `closed (${event.code})`;
      this.options.handlers.onConnection(false, reason);
      if (!this.closed) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.timer = setTimeout(() => {
      this.timer = null;
      this.connect();
    }, this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, RECONNECT_MAX_MS);
  }

  private receive(socket: WebSocket, raw: string): void {
    let json: unknown;
    try {
      json = JSON.parse(raw);
    } catch {
      return;
    }
    const frame = ServerFrameSchema.safeParse(json);
    if (!frame.success) return;
    const data = frame.data;
    if (data.op === "ack" && data.req_id === AUTH_REQ_ID && data.ok) {
      this.retryMs = RECONNECT_MIN_MS;
      this.options.handlers.onConnection(true, "connected");
      for (const channel of [...CHANNELS, ...(this.options.sessionChannels ?? [])]) {
        socket.send(JSON.stringify({ op: "subscribe", req_id: `s${this.nextReq++}`, channel }));
      }
    } else if (data.op === "msg" && data.type === "system.metrics") {
      const metrics = SystemMetricsSchema.safeParse(data.data);
      if (metrics.success) this.options.handlers.onMetrics(metrics.data);
    } else if (data.op === "msg" && data.type === "safety.state") {
      const safety = SafetyStateSchema.safeParse(data.data);
      if (safety.success) this.options.handlers.onSafety(safety.data);
    } else if (data.op === "msg" && data.type === "telemetry.frame") {
      const frame = TelemetryFrameUISchema.safeParse(data.data);
      if (frame.success) this.options.handlers.onTelemetryFrame?.(frame.data);
    } else if (data.op === "msg" && data.type === "game.event") {
      const event = GameEventSchema.safeParse(data.data);
      if (event.success) this.options.handlers.onGameEvent?.(event.data);
    }
  }
}
