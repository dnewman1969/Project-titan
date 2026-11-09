import { BETA_TEST_PLAYBOOK_URL, findMenuItem } from "../../../shared/menu";
import type { AppDispatch, RootState } from "../../app/store";
import { getTitan } from "../../app/runtime";
import { openSessionDialog, requestRecordingFromMenu } from "../sessions/sessionsSlice";
import { setAboutOpen, setFirstRunOpen, showNotice, togglePanel } from "./layoutSlice";

export function handleMenuCommand(id: string, dispatch: AppDispatch, getState: () => RootState): void {
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
  if (item.id === "help.betaTest") {
    void getTitan().openExternal(BETA_TEST_PLAYBOOK_URL);
    return;
  }
  if (item.id === "record.openFolder") {
    const root = getState().sessions.recordingRootDir;
    if (!root) {
      dispatch(showNotice("Start a recording first, or open the session folder from API logs."));
      return;
    }
    void getTitan()
      .openPath(root)
      .then((err) => {
        if (err) dispatch(showNotice(`Could not open folder: ${err}`));
      });
    return;
  }
  dispatch(
    showNotice(
      item.milestone ? `${item.label} arrives in ${item.milestone}.` : `${item.label} is not available yet.`,
    ),
  );
}
