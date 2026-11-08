# ADR 0010: Recording (D10)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D10 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Recording for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

OBS Studio 30+ driven over **obs-websocket v5** for gameplay video and audio tracks. Titan's capture worker runs **FFmpeg** for the webcam as a separate file

## Alternatives rejected

Custom DXGI recorder in Phase 1

## Rationale

OBS already does game capture, NVENC, and multi-track lossless audio reliably. Webcam goes to a separate file to meet the "independent tracks" rule. Titan owns the webcam device and gives the UI an MJPEG preview.

## Consequences

- OBS Studio 30+ with obs-websocket v5 is a prerequisite checked by the first-run wizard.
- The capture worker owns the webcam device, records it with FFmpeg to its own file and serves an MJPEG preview.
