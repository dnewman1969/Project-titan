import { useEffect } from "react";

import { hydrateFromSettings } from "../features/operations/layoutSlice";
import { useGetSettingsQuery } from "./api";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";

/** Loads panel visibility from GET /settings (M7.T1). Persistence on toggle is handled in the store listener. */
export function useLayoutSettings(): void {
  const dispatch = useAppDispatch();
  const skip = getTitan().backend === "none";
  const { data } = useGetSettingsQuery(undefined, { skip });

  useEffect(() => {
    if (!data) return;
    dispatch(hydrateFromSettings(data));
  }, [data, dispatch]);
}
