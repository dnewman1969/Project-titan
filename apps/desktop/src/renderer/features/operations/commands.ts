import { findMenuItem } from "../../../shared/menu";
import type { AppDispatch } from "../../app/store";
import { setAboutOpen, showNotice, togglePanel } from "./layoutSlice";

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
  dispatch(
    showNotice(
      item.milestone ? `${item.label} arrives in ${item.milestone}.` : `${item.label} is not available yet.`,
    ),
  );
}
