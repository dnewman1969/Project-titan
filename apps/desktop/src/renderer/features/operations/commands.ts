import { BETA_TEST_PLAYBOOK_URL, DOCS_URL, findMenuItem } from "../../../shared/menu";
import type { AppDispatch, RootState } from "../../app/store";
import { getTitan } from "../../app/runtime";
import { engageKill } from "../safety/engageKill";
import { openSessionDialog, requestRecordingFromMenu } from "../sessions/sessionsSlice";
import {
  setAboutOpen,
  setFirstRunOpen,
  setKrpcObsHelpOpen,
  setMemoryBrowserOpen,
  setPublishOpen,
  showNotice,
  showPanel,
  togglePanel,
} from "./layoutSlice";

export function handleMenuCommand(id: string, dispatch: AppDispatch, getState: () => RootState): void {
  const item = findMenuItem(id);
  if (!item) return;
  if (item.kind === "toggle") {
    dispatch(togglePanel(item.panel));
    return;
  }
  switch (item.id) {
    case "file.newSession":
      dispatch(openSessionDialog("new"));
      return;
    case "ai.memoryBrowser":
      dispatch(setMemoryBrowserOpen(true));
      return;
    case "record.start":
      dispatch(requestRecordingFromMenu("start"));
      return;
    case "record.stop":
      dispatch(requestRecordingFromMenu("stop"));
      return;
    case "record.openFolder": {
      const root = getState().sessions.recordingRootDir;
      if (!root) {
        dispatch(showNotice("Start a recording first, then open its folder from Record."));
        return;
      }
      void getTitan()
        .openPath(root)
        .then((err) => {
          if (err) dispatch(showNotice(`Could not open folder: ${err}`));
        });
      return;
    }
    case "tools.gameDiscovery":
      dispatch(showPanel("games"));
      return;
    case "tools.youtubePublish":
      dispatch(setPublishOpen(true));
      return;
    case "tools.logs":
      dispatch(showPanel("events"));
      return;
    case "tools.killSwitch":
      engageKill(dispatch);
      return;
    case "help.docs":
      void getTitan().openExternal(DOCS_URL);
      return;
    case "help.betaTest":
      void getTitan().openExternal(BETA_TEST_PLAYBOOK_URL);
      return;
    case "help.firstRun":
      dispatch(setFirstRunOpen(true));
      return;
    case "help.krpcObs":
      dispatch(setKrpcObsHelpOpen(true));
      return;
    case "help.about":
      dispatch(setAboutOpen(true));
      return;
    default:
      return;
  }
}
