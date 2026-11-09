import { combineReducers, configureStore } from "@reduxjs/toolkit";

import { agentsChatSlice } from "../features/agents/agentsChatSlice";
import { eventsSlice } from "../features/events/eventsSlice";
import { layoutSlice } from "../features/operations/layoutSlice";
import { safetySlice } from "../features/safety/safetySlice";
import { sessionsSlice } from "../features/sessions/sessionsSlice";
import { supervisorSlice } from "../features/system/supervisorSlice";
import { gameTelemetrySlice } from "../features/telemetry/gameTelemetrySlice";
import { systemSlice } from "../features/telemetry/systemSlice";
import { titanApi } from "./api";
import { layoutPersistListener } from "./layoutPersistListener";

const rootReducer = combineReducers({
  [titanApi.reducerPath]: titanApi.reducer,
  layout: layoutSlice.reducer,
  safety: safetySlice.reducer,
  events: eventsSlice.reducer,
  agentsChat: agentsChatSlice.reducer,
  system: systemSlice.reducer,
  gameTelemetry: gameTelemetrySlice.reducer,
  sessions: sessionsSlice.reducer,
  supervisor: supervisorSlice.reducer,
});

export type RootState = ReturnType<typeof rootReducer>;

export function makeStore(preloadedState?: Partial<RootState>) {
  return configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefault) => getDefault().concat(titanApi.middleware, layoutPersistListener.middleware),
  });
}

export type AppStore = ReturnType<typeof makeStore>;
export type AppDispatch = AppStore["dispatch"];

/** Single renderer store (menu commands read state outside React). */
export const appStore = makeStore();
