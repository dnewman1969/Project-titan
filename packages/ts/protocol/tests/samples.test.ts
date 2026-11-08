// Round-trip test (M0.T4): the shared contract samples validate with the generated zod schemas
// exactly as they do with Pydantic and JSON Schema (tests/contract/test_protocol_roundtrip.py).
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";
import type { ZodTypeAny } from "zod";

import * as protocol from "../src";

const SAMPLES = join(import.meta.dirname, "..", "..", "..", "..", "tests", "contract", "samples");

interface Case {
  def?: string;
  byType?: boolean;
  valid?: unknown[];
  invalid?: unknown[];
}

interface TypedItem {
  type: string;
  payload: unknown;
}

function schemaFor(name: string): ZodTypeAny {
  const schema = (protocol as unknown as Record<string, ZodTypeAny | undefined>)[`${name}Schema`];
  if (!schema) throw new Error(`no generated schema ${name}Schema`);
  return schema;
}

function payloadSchema(type: string): ZodTypeAny {
  if (!protocol.isMessageType(type)) throw new Error(`unknown message type ${type}`);
  return protocol.MESSAGE_PAYLOAD_SCHEMAS[type];
}

const rows: { id: string; schema: ZodTypeAny; item: unknown; ok: boolean }[] = [];
for (const file of readdirSync(SAMPLES).filter((f) => f.endsWith(".json"))) {
  const data = JSON.parse(readFileSync(join(SAMPLES, file), "utf-8")) as Case & { cases?: Case[] };
  for (const [i, c] of (data.cases ?? [data]).entries()) {
    for (const [ok, items] of [
      [true, c.valid ?? []],
      [false, c.invalid ?? []],
    ] as const) {
      items.forEach((raw, n) => {
        const typed = raw as TypedItem;
        const schema = c.byType ? payloadSchema(typed.type) : schemaFor(c.def ?? "");
        const label = c.byType ? typed.type : (c.def ?? "");
        rows.push({
          id: `${file}[${i}] ${label} ${ok ? "ok" : "bad"}${n}`,
          schema,
          item: c.byType ? typed.payload : raw,
          ok,
        });
      });
    }
  }
}

describe("contract samples", () => {
  it("has samples", () => {
    expect(rows.length).toBeGreaterThanOrEqual(40);
  });

  it.each(rows)("$id", ({ schema, item, ok }) => {
    expect(schema.safeParse(item).success).toBe(ok);
  });
});

describe("helpers", () => {
  it("parses envelope payloads by type", () => {
    const data = JSON.parse(readFileSync(join(SAMPLES, "envelope.json"), "utf-8")) as Case;
    for (const raw of data.valid ?? []) {
      const env = protocol.EnvelopeSchema.parse(raw);
      const type = env.type;
      expect(protocol.isMessageType(type)).toBe(true);
      if (protocol.isMessageType(type)) {
        const typed = { ...env, type };
        expect(() => protocol.parseEnvelopePayload(typed)).not.toThrow();
      }
    }
  });

  it("parses ws msg data by type", () => {
    const frame = protocol.MsgFrameSchema.parse({
      op: "msg",
      channel: "session.x.chat",
      seq: "1-0",
      ts: "2026-11-08T19:30:01.234Z",
      type: "chat.delta",
      data: { message_id: "0193f1a2-8000-7000-8000-000000000004", delta: "hi" },
    });
    expect(protocol.isWsMessageType(frame.type)).toBe(true);
    if (protocol.isWsMessageType(frame.type)) {
      expect(protocol.parseWsData({ ...frame, type: frame.type })).toMatchObject({ delta: "hi" });
    }
  });
});
