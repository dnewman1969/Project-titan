import { combineReducers, configureStore } from "@reduxjs/toolkit";

import { eventsSlice } from "../features/events/eventsSlice";
import { layoutSlice } from "../features/operations/layoutSlice";
import { safetySlice } from "../features/safety/safetySlice";
import { supervisorSlice } from "../features/system/supervisorSlice";
import { systemSlice } from "../features/telemetry/systemSlice";
import { titanApi } from "./api";

const rootReducer = combineReducers({
  [titanApi.reducerPath]: titanApi.reducer,
  layout: layoutSlice.reducer,
  safety: safetySlice.reducer,
  events: eventsSlice.reducer,
  system: systemSlice.reducer,
  supervisor: supervisorSlice.reducer,
});

export type RootState = ReturnType<typeof rootReducer>;

export function makeStore(preloadedState?: Partial<RootState>) {
  return configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefault) => getDefault().concat(titanApi.middleware),
  });
}

export type AppStore = ReturnType<typeof makeStore>;
export type AppDispatch = AppStore["dispatch"];
