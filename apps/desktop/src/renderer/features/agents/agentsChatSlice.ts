import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface AgentChatLine {
  id: string;
  persona_slug: string;
  display_name: string;
  role: string;
  text: string;
  at_ms: number;
}

interface AgentsChatState {
  lines: AgentChatLine[];
  speakingSlug: string | null;
}

const initialState: AgentsChatState = { lines: [], speakingSlug: null };

let seq = 0;

export const agentsChatSlice = createSlice({
  name: "agentsChat",
  initialState,
  reducers: {
    agentSaid(state, action: PayloadAction<Omit<AgentChatLine, "id" | "at_ms"> & { at_ms?: number }>) {
      state.lines.push({
        ...action.payload,
        id: `line-${++seq}`,
        at_ms: action.payload.at_ms ?? Date.now(),
      });
      if (state.lines.length > 80) state.lines.shift();
    },
    setSpeaking(state, action: PayloadAction<string | null>) {
      state.speakingSlug = action.payload;
    },
    clearAgentChat(state) {
      state.lines = [];
      state.speakingSlug = null;
    },
  },
});

export const { agentSaid, setSpeaking, clearAgentChat } = agentsChatSlice.actions;
