import { describe, expect, it } from "vitest";

import {
  buildComfyPortraitUrl,
  buildStaticPortraitUrl,
  portraitSlugKey,
  resolvePortraitUrl,
} from "../../src/renderer/services/avatar/portrait";

describe("ComfyUI portrait helpers", () => {
  it("shortens seeded persona slugs for Comfy filenames", () => {
    expect(portraitSlugKey("ksp.director.wernher")).toBe("wernher");
    expect(portraitSlugKey("jeb-radio")).toBe("jeb-radio");
    expect(portraitSlugKey("Val")).toBe("val");
  });

  it("builds Comfy /view URLs for titan-{slug}.png output", () => {
    expect(buildComfyPortraitUrl("http://127.0.0.1:8188/view", "ksp.navigator.val")).toBe(
      "http://127.0.0.1:8188/view?filename=titan-val.png&type=output",
    );
  });

  it("prefers live override, then Comfy, then static base", () => {
    expect(
      resolvePortraitUrl({
        personaSlug: "wernher",
        overrideUrl: "http://cdn.example/w.png",
        comfyViewUrl: "http://127.0.0.1:8188/view",
      }),
    ).toBe("http://cdn.example/w.png");

    expect(
      resolvePortraitUrl({
        personaSlug: "gene",
        comfyViewUrl: "http://127.0.0.1:8188/view/",
      }),
    ).toContain("filename=titan-gene.png");

    expect(
      resolvePortraitUrl({
        personaSlug: "linus",
        portraitBase: "http://127.0.0.1:9000/portraits",
      }),
    ).toBe("http://127.0.0.1:9000/portraits/linus.png");

    expect(resolvePortraitUrl({ personaSlug: "wernher" })).toBe("/portraits/wernher.png");
  });

  it("builds static portrait paths", () => {
    expect(buildStaticPortraitUrl("/portraits", "ksp.flight_engineer.gene")).toBe("/portraits/gene.png");
  });
});
