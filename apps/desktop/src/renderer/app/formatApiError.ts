import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";

function detailFromData(data: unknown): string | null {
  if (typeof data === "string" && data.length > 0) {
    return data;
  }
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const detail = Reflect.get(data, "detail");
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  const title = Reflect.get(data, "title");
  const code = Reflect.get(data, "code");
  if (typeof code === "string" && typeof title === "string") {
    return `${code}: ${title}`;
  }
  const errors = Reflect.get(data, "errors");
  if (Array.isArray(errors) && errors.length > 0) {
    const first = errors[0];
    if (typeof first === "object" && first !== null) {
      const msg = Reflect.get(first, "message");
      const field = Reflect.get(first, "field");
      if (typeof msg === "string") {
        return typeof field === "string" && field ? `${field}: ${msg}` : msg;
      }
    }
  }
  return null;
}

/** RFC 7807 problem+json and RTK fetch errors into a single user-visible line. */
export function formatApiError(error: unknown): string {
  if (error === undefined || error === null) {
    return "Unknown API error";
  }
  const rtk = error as FetchBaseQueryError;
  if (rtk.status === "PARSING_ERROR" || rtk.status === "CUSTOM_ERROR") {
    const err = rtk.error;
    if (typeof err === "string") {
      return `Invalid API response: ${err}`;
    }
    if (err !== undefined && err !== null) {
      return `Invalid API response: ${formatApiError(err)}`;
    }
    return "Invalid API response (schema parse failed)";
  }
  if (typeof rtk.status === "number") {
    const detail = detailFromData(rtk.data);
    if (detail) {
      return `HTTP ${rtk.status}: ${detail}`;
    }
    if (rtk.error) {
      return `HTTP ${rtk.status}: ${rtk.error}`;
    }
    return `HTTP ${rtk.status}`;
  }
  if (typeof rtk === "object" && "message" in rtk && typeof rtk.message === "string") {
    return rtk.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
