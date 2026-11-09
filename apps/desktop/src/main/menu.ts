import type { MenuItemConstructorOptions } from "electron";

import { MENU, type MenuEntry, type MenuSection } from "../shared/menu";

export interface MenuHandlers {
  /** Forward a command to the renderer. */
  send: (id: string) => void;
  openDocs: () => void;
}

function toItem(entry: MenuEntry, handlers: MenuHandlers): MenuItemConstructorOptions {
  switch (entry.kind) {
    case "separator":
      return { type: "separator" };
    case "role":
      return entry.label ? { role: entry.role, label: entry.label } : { role: entry.role };
    case "toggle":
      return {
        id: entry.id,
        label: entry.label,
        type: "checkbox",
        checked: true,
        click: () => {
          handlers.send(entry.id);
        },
      };
    case "command":
      return {
        id: entry.id,
        label: entry.label,
        ...(entry.accelerator ? { accelerator: entry.accelerator } : {}),
        click: () => {
          if (entry.id === "help.docs") handlers.openDocs();
          else handlers.send(entry.id);
        },
      };
  }
}

export function buildMenuTemplate(
  handlers: MenuHandlers,
  { dev, menu = MENU }: { dev: boolean; menu?: readonly MenuSection[] },
): MenuItemConstructorOptions[] {
  return menu.map((section) => {
    const submenu = section.items.map((entry) => toItem(entry, handlers));
    if (dev && section.label === "View") {
      submenu.push({ type: "separator" }, { role: "reload" }, { role: "toggleDevTools" });
    }
    return { label: section.label, submenu };
  });
}
