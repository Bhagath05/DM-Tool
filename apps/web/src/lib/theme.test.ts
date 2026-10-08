/**
 * Phase 6.6 — theme module: persistence, <html data-theme> application,
 * and the FOUC bootstrap script.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  __resetThemeForTests,
  applyThemeChoice,
  getThemeChoice,
  resolveTheme,
  setThemeChoice,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
} from "./theme";

beforeEach(() => __resetThemeForTests());
afterEach(() => __resetThemeForTests());

describe("theme choice persistence", () => {
  it("defaults to system when nothing is stored", () => {
    expect(getThemeChoice()).toBe("system");
  });

  it("persists an explicit choice and reads it back", () => {
    setThemeChoice("dark");
    expect(getThemeChoice()).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("clears storage (and the attribute) when set back to system", () => {
    setThemeChoice("light");
    setThemeChoice("system");
    expect(getThemeChoice()).toBe("system");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});

describe("applyThemeChoice → <html data-theme>", () => {
  it("sets the attribute for an explicit choice", () => {
    applyThemeChoice("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    applyThemeChoice("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("removes the attribute for system so the OS media query governs", () => {
    applyThemeChoice("dark");
    applyThemeChoice("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});

describe("resolveTheme", () => {
  it("returns the forced value regardless of the OS", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("falls back to light for system when matchMedia is unavailable", () => {
    // jsdom has no matchMedia by default → the guard returns light.
    expect(resolveTheme("system")).toBe("light");
  });
});

describe("THEME_INIT_SCRIPT", () => {
  it("references the storage key and is self-contained (IIFE + try/catch)", () => {
    expect(THEME_INIT_SCRIPT).toContain(THEME_STORAGE_KEY);
    expect(THEME_INIT_SCRIPT).toContain("try");
    expect(THEME_INIT_SCRIPT).toContain("data-theme");
  });
});
