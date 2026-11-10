/**
 * Tracks a game HWND and keeps it locked to the Operations Center preview.
 * The Win32 calls live behind EmbedHost so this state machine runs in unit tests.
 */
import type { GameViewRect, GameViewStatus } from "../../shared/ipc";

import {
  blankStatus,
  COVERING_CHROME_REASON,
  exesForSlug,
  exeBase,
  initialMode,
  pickWindow,
  rectCoversSessionChrome,
  waitingReason,
  type EmbedMode,
  type EmbedPreference,
  type FoundWindow,
  type ProbeResult,
} from "./protocol";

export interface ApplyRequest {
  mode: EmbedMode;
  hwnd: string;
  anchor: string;
  rect: GameViewRect;
}

export interface PlaceRequest {
  hwnd: string;
  mode: EmbedMode;
  anchor: string;
  rect: GameViewRect;
}

export interface HostResult {
  ok: boolean;
  error: string | null;
}

export interface EmbedHost {
  available(): boolean;
  start(): Promise<void>;
  find(exes: string[]): Promise<FoundWindow[]>;
  apply(request: ApplyRequest): Promise<HostResult>;
  place(request: PlaceRequest): Promise<HostResult>;
  probe(hwnd: string): Promise<ProbeResult>;
  setVisible(hwnd: string, visible: boolean): Promise<HostResult>;
  release(hwnd: string): Promise<void>;
  releaseAll(): Promise<void>;
  focus(hwnd: string): Promise<void>;
  stop(): Promise<void>;
}

export interface GameViewControllerOptions {
  host: EmbedHost;
  electronHwnd: () => string | null;
  mapRect: (viewport: GameViewRect, mode: EmbedMode) => GameViewRect | null;
  /** Content height of the Titan window, in DIP. When set, a rect that covers the chrome is not placed. */
  contentHeight?: () => number;
  preference?: EmbedPreference;
  now?: () => number;
  /** How long an embed may fail to stay a child before we dock instead. */
  embedGraceMs?: number;
  /** Preview must be at least this large before we move the game onto it. */
  minEdge?: number;
}

interface Attached {
  hwnd: string;
  mode: EmbedMode;
  pid: number;
  title: string;
  exe: string;
}

const WINDOWS_ONLY = "The live game locks into this frame on Windows.";

export class GameViewController {
  private readonly host: EmbedHost;
  private readonly electronHwnd: () => string | null;
  private readonly mapRect: (viewport: GameViewRect, mode: EmbedMode) => GameViewRect | null;
  private readonly contentHeight: (() => number) | null;
  private readonly preference: EmbedPreference;
  private readonly now: () => number;
  private readonly embedGraceMs: number;
  private readonly minEdge: number;

  private slug: string | null = null;
  private pid: number | null = null;
  private viewport: GameViewRect | null = null;
  private attached: Attached | null = null;
  private embedAttemptAt = 0;
  private embedConfirmed = false;
  private hidden = false;
  private readonly holds = new Set<string>();
  private status: GameViewStatus = blankStatus(null);
  private readonly listeners = new Set<(status: GameViewStatus) => void>();
  private chain: Promise<void> = Promise.resolve();
  private closed = false;
  private broken: string | null = null;
  private starting: Promise<void> | null = null;

  constructor(options: GameViewControllerOptions) {
    this.host = options.host;
    this.electronHwnd = options.electronHwnd;
    this.mapRect = options.mapRect;
    this.contentHeight = options.contentHeight ?? null;
    this.preference = options.preference ?? "auto";
    this.now = options.now ?? Date.now;
    this.embedGraceMs = options.embedGraceMs ?? 500;
    this.minEdge = options.minEdge ?? 32;
  }

  onStatus(listener: (status: GameViewStatus) => void): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => {
      this.listeners.delete(listener);
    };
  }

  currentStatus(): GameViewStatus {
    return this.status;
  }

  setTarget(target: { gameSlug: string | null; pid: number | null }): void {
    const slugChanged = target.gameSlug !== this.slug;
    this.slug = target.gameSlug;
    this.pid = target.pid;
    if (slugChanged && this.attached && !this.exeMatchesSlug(this.attached.exe)) {
      void this.detachThenTick();
      return;
    }
    void this.tick(true);
  }

  setViewport(rect: GameViewRect): void {
    this.viewport = rect;
    void this.tick(false);
  }

  setHold(reason: string, on: boolean): void {
    if (on) this.holds.add(reason);
    else this.holds.delete(reason);
    void this.tick(true);
  }

  focus(): void {
    void this.focusNow();
  }

  /** Full discovery when `discover` is true; otherwise only reposition an attached window. */
  tick(discover = true): Promise<void> {
    if (this.closed) return this.chain;
    const run = this.chain.then(async () => {
      if (this.closed) return;
      try {
        await this.step(discover || !this.attached);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Game view failed";
        this.publish(this.attached ? this.statusOf(message) : blankStatus(message));
      }
    });
    this.chain = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  async shutdown(): Promise<{ hwnd: string | null; released: boolean }> {
    this.closed = true;
    await this.chain;
    const hwnd = this.attached?.hwnd ?? null;
    this.attached = null;
    this.hidden = false;
    let released = true;
    try {
      await Promise.race([
        this.host.releaseAll(),
        new Promise<never>((_resolve, reject) => {
          setTimeout(() => {
            reject(new Error("timeout"));
          }, 1200);
        }),
      ]);
    } catch {
      released = false;
    }
    try {
      await this.host.stop();
    } catch {
      released = false;
    }
    return { hwnd, released };
  }

  private async focusNow(): Promise<void> {
    if (!this.attached) await this.tick(true);
    const hwnd = this.attached?.hwnd;
    if (!hwnd) return;
    await this.host.focus(hwnd);
    await this.tick(false);
  }

  private async detachThenTick(): Promise<void> {
    const hwnd = this.attached?.hwnd;
    this.attached = null;
    this.embedConfirmed = false;
    this.hidden = false;
    if (hwnd) {
      try {
        await this.host.release(hwnd);
      } catch {
        /* the next discovery pass will pick up whatever is still on screen */
      }
    }
    await this.tick(true);
  }

  private async ensureHost(): Promise<void> {
    if (!this.starting) {
      this.starting = this.host.start().catch((error: unknown) => {
        this.broken = error instanceof Error ? error.message : "Game view host failed to start";
      });
    }
    await this.starting;
  }

  private hasFrame(): boolean {
    const viewport = this.viewport;
    return Boolean(viewport && viewport.width >= this.minEdge && viewport.height >= this.minEdge);
  }

  /** A real preview that would paint over the session bar or the status strip. */
  private coveringChrome(): boolean {
    const viewport = this.viewport;
    if (!this.hasFrame() || !viewport || !this.contentHeight) return false;
    return rectCoversSessionChrome(viewport, this.contentHeight());
  }

  private mapped(mode: EmbedMode): GameViewRect | null {
    const viewport = this.viewport;
    if (!viewport || viewport.width < this.minEdge || viewport.height < this.minEdge) return null;
    return this.mapRect(viewport, mode);
  }

  private exeMatchesSlug(exe: string): boolean {
    if (!this.slug) return true;
    return exesForSlug(this.slug).includes(exeBase(exe));
  }

  private anchor(): string | null {
    const hwnd = this.electronHwnd();
    if (!hwnd || hwnd === "0") return null;
    return hwnd;
  }

  private async step(discover: boolean): Promise<void> {
    await this.ensureHost();
    if (this.closed) return;
    if (this.broken || !this.host.available()) {
      this.publish(blankStatus(this.broken ?? WINDOWS_ONLY));
      return;
    }
    const anchor = this.anchor();
    if (!anchor) {
      this.publish(blankStatus("Titan window is not ready"));
      return;
    }

    if (this.holds.size > 0) {
      if (this.attached && !this.hidden) {
        await this.host.setVisible(this.attached.hwnd, false);
        this.hidden = true;
      }
      const reason = this.attached ? null : waitingReason(this.slug);
      this.publish(this.attached ? this.statusOf(reason) : blankStatus(reason));
      return;
    }

    if (this.coveringChrome()) {
      if (this.attached && !this.hidden) {
        await this.host.setVisible(this.attached.hwnd, false);
        this.hidden = true;
      }
      this.publish(blankStatus(COVERING_CHROME_REASON));
      return;
    }

    if (!discover && this.attached) {
      if (this.hidden) {
        await this.host.setVisible(this.attached.hwnd, true);
        this.hidden = false;
      }
      await this.reposition();
      return;
    }

    if (this.attached) {
      const probe = await this.host.probe(this.attached.hwnd);
      if (!probe.alive) {
        this.attached = null;
        this.embedConfirmed = false;
        this.hidden = false;
      } else if (this.attached.mode === "embed" && !this.embedConfirmed) {
        const stuck = probe.parent === anchor && probe.width >= 2 && probe.height >= 2;
        if (stuck) this.embedConfirmed = true;
        else if (this.now() - this.embedAttemptAt >= this.embedGraceMs) {
          await this.fallbackToDock(anchor);
          return;
        }
      }
    }

    if (!this.attached) {
      if (!this.hasFrame()) {
        this.publish(blankStatus("Waiting for the preview frame"));
        return;
      }
      const found = await this.host.find(exesForSlug(this.slug));
      const picked = pickWindow(found, this.pid);
      if (!picked) {
        this.publish(blankStatus(waitingReason(this.slug)));
        return;
      }
      await this.attach(picked, initialMode(picked, this.preference), anchor, true);
      return;
    }

    if (this.hidden) {
      await this.host.setVisible(this.attached.hwnd, true);
      this.hidden = false;
    }
    await this.reposition();
  }

  private async attach(
    win: FoundWindow,
    mode: EmbedMode,
    anchor: string,
    allowFallback: boolean,
  ): Promise<void> {
    const rect = this.mapped(mode);
    if (!rect) {
      this.publish(blankStatus("Waiting for the preview frame"));
      return;
    }
    const result = await this.host.apply({ mode, hwnd: win.hwnd, anchor, rect });
    if (!result.ok) {
      if (mode === "embed" && allowFallback) {
        try {
          await this.host.release(win.hwnd);
        } catch {
          /* embed never saved state */
        }
        await this.attach(win, "dock", anchor, false);
        return;
      }
      this.publish(blankStatus(result.error ?? "Could not lock the game window"));
      return;
    }
    this.attached = { hwnd: win.hwnd, mode, pid: win.pid, title: win.title, exe: win.exe };
    this.embedAttemptAt = this.now();
    this.embedConfirmed = mode !== "embed";
    this.hidden = false;
    if (this.holds.size > 0) {
      await this.host.setVisible(win.hwnd, false);
      this.hidden = true;
    }
    this.publish(this.statusOf(null));
  }

  private async fallbackToDock(anchor: string): Promise<void> {
    const current = this.attached;
    if (!current) return;
    try {
      await this.host.release(current.hwnd);
    } catch {
      /* still try to dock the same hwnd */
    }
    this.attached = null;
    this.hidden = false;
    await this.attach(
      {
        hwnd: current.hwnd,
        pid: current.pid,
        title: current.title,
        exe: current.exe,
        className: "",
        width: 0,
        height: 0,
      },
      "dock",
      anchor,
      false,
    );
  }

  private async reposition(): Promise<void> {
    const current = this.attached;
    if (!current) return;
    const rect = this.mapped(current.mode);
    if (!rect) return;
    const anchor = this.anchor();
    if (!anchor) return;
    const result = await this.host.place({ hwnd: current.hwnd, mode: current.mode, anchor, rect });
    if (!result.ok) {
      if (/gone/i.test(result.error ?? "")) {
        this.attached = null;
        this.publish(blankStatus(waitingReason(this.slug)));
        return;
      }
      this.publish(this.statusOf(result.error));
      return;
    }
    this.publish(this.statusOf(null));
  }

  private statusOf(reason: string | null): GameViewStatus {
    const attached = this.attached;
    if (!attached) return blankStatus(reason);
    return {
      attached: true,
      mode: attached.mode,
      title: attached.title,
      exe: attached.exe,
      pid: attached.pid,
      reason,
    };
  }

  private publish(status: GameViewStatus): void {
    if (JSON.stringify(status) === JSON.stringify(this.status)) return;
    this.status = status;
    for (const listener of this.listeners) listener(status);
  }
}
