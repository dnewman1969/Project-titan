import { findMenuItem } from "../../../shared/menu";
import type { AppDispatch } from "../../app/store";
import { openSessionDialog, requestRecordingFromMenu } from "../sessions/sessionsSlice";
import { setAboutOpen, setFirstRunOpen, showNotice, togglePanel } from "./layoutSlice";

export function handleMenuCommand(id: string, dispatch: AppDispatch): void {
  const item = findMenuItem(id);
  if (!item) return;
  if (item.kind === "toggle") {
    dispatch(togglePanel(item.panel));
    return;
  }
  if (item.id === "help.about") {
    dispatch(setAboutOpen(true));
    return;
  }
  if (item.id === "file.newSession") {
    dispatch(openSessionDialog("new"));
    return;
  }
  if (item.id === "tools.gameDiscovery") {
    dispatch(togglePanel("games"));
    return;
  }
  if (item.id === "help.firstRun") {
    dispatch(setFirstRunOpen(true));
    return;
  }
  if (item.id === "record.start") {
    dispatch(requestRecordingFromMenu("start"));
    return;
  }
  if (item.id === "record.stop") {
    dispatch(requestRecordingFromMenu("stop"));
    return;
  }
  dispatch(
    showNotice(
      item.milestone ? `${item.label} arrives in ${item.milestone}.` : `${item.label} is not available yet.`,
    ),
  );
}
