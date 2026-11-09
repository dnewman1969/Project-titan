import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type LearnKind = "discovery" | "lesson" | "outcome";

export interface LearnItem {
  id: string;
  kind: LearnKind;
  text: string;
  ok: boolean | null;
  actionId: string | null;
  at_ms: number;
}

interface LearnState {
  items: LearnItem[];
}

const initialState: LearnState = { items: [] };

let seq = 0;

export const learnSlice = createSlice({
  name: "learn",
  initialState,
  reducers: {
    learnItemReceived(
      state,
      action: PayloadAction<{
        key: string;
        kind: LearnKind;
        text: string;
        ok?: boolean | null;
        actionId?: string | null;
        at_ms?: number;
      }>,
    ) {
      const id = action.payload.key || `learn-${++seq}`;
      if (state.items.some((row) => row.id === id)) return;
      state.items.unshift({
        id,
        kind: action.payload.kind,
        text: action.payload.text,
        ok: action.payload.ok ?? null,
        actionId: action.payload.actionId ?? null,
        at_ms: action.payload.at_ms ?? Date.now(),
      });
      if (state.items.length > 40) state.items.pop();
    },
    clearLearnItems(state) {
      state.items = [];
    },
  },
});

export const { learnItemReceived, clearLearnItems } = learnSlice.actions;
