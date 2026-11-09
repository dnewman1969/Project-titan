import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function detailFromData(data: unknown): string | null {
  if (typeof data === "string" && data.length > 0) {
    return data;
  }
  if (!isRecord(data)) {
    return null;
  }
  const detail = data.detail;
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  const title = data.title;
  const code = data.code;
  if (typeof code === "string" && typeof title === "string") {
    return `${code}: ${title}`;
  }
  const errors = data.errors;
  if (Array.isArray(errors) && errors.length > 0) {
    const first: unknown = errors[0];
    if (isRecord(first)) {
      const msg = first.message;
      const field = first.field;
      if (typeof msg === "string") {
        return typeof field === "string" && field.length > 0 ? `${field}: ${msg}` : msg;
      }
    }
  }
  return null;
}

function isFetchBaseQueryError(error: object): error is FetchBaseQueryError {
  return "status" in error;
}

/** RFC 7807 problem+json and RTK fetch errors into a single user-visible line. */
export function formatApiError(error: unknown): string {
  if (error === undefined || error === null) {
    return "Unknown API error";
  }
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  if (typeof error !== "object") {
    return "Unknown API error";
  }
  if (isFetchBaseQueryError(error)) {
    if (error.status === "PARSING_ERROR" || error.status === "CUSTOM_ERROR") {
      const parseErr: unknown = error.error;
      if (typeof parseErr === "string") {
        return `Invalid API response: ${parseErr}`;
      }
      if (isRecord(parseErr) && typeof parseErr.message === "string") {
        return `Invalid API response: ${parseErr.message}`;
      }
      return "Invalid API response (schema parse failed)";
    }
    if (typeof error.status === "number") {
      const detail = detailFromData(error.data);
      if (detail) {
        return `HTTP ${String(error.status)}: ${detail}`;
      }
      if ("error" in error) {
        const errField = (error as { error?: unknown }).error;
        if (typeof errField === "string") {
          return `HTTP ${String(error.status)}: ${errField}`;
        }
      }
      return `HTTP ${String(error.status)}`;
    }
  }
  if ("message" in error && typeof error.message === "string") {
    return error.message;
  }
  return "Unknown API error";
}
