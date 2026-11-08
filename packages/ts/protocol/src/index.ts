import type { z } from "zod";

import { MESSAGE_PAYLOAD_SCHEMAS, WS_DATA_SCHEMAS, type Envelope, type MsgFrame } from "./generated/protocol";

export * from "./generated/protocol";

export const ENVELOPE_SCHEMA = "titan.msg/1";
export const TELEMETRY_SCHEMA = "titan.telemetry/1";
export const WS_CLOSE_UNAUTHORIZED = 4401;
export const WS_CLOSE_BACKPRESSURE = 4408;

export type MessageType = keyof typeof MESSAGE_PAYLOAD_SCHEMAS;
export type WsMessageType = keyof typeof WS_DATA_SCHEMAS;

export function isMessageType(type: string): type is MessageType {
  return Object.hasOwn(MESSAGE_PAYLOAD_SCHEMAS, type);
}

export function isWsMessageType(type: string): type is WsMessageType {
  return Object.hasOwn(WS_DATA_SCHEMAS, type);
}

/** Validate an envelope's payload against the schema selected by its `type` (Section 6.2). */
export function parseEnvelopePayload<T extends MessageType>(
  envelope: Envelope & { type: T },
): z.infer<(typeof MESSAGE_PAYLOAD_SCHEMAS)[T]> {
  const schema = MESSAGE_PAYLOAD_SCHEMAS[envelope.type];
  return schema.parse(envelope.payload);
}

/** Validate the `data` of a WebSocket `msg` frame against the schema for its `type` (Section 5.3). */
export function parseWsData<T extends WsMessageType>(
  frame: MsgFrame & { type: T },
): z.infer<(typeof WS_DATA_SCHEMAS)[T]> {
  const schema = WS_DATA_SCHEMAS[frame.type];
  return schema.parse(frame.data);
}
