"use client";

/**
 * Topbar control to switch theme: System · Light · Dark.
 *
 * Mirrors ViewModeToggle (segmented radiogroup) so the two topbar controls
 * read as a pair. The choice persists via lib/theme.ts and is applied to
 * <html data-theme> immediately; "System" tracks the OS. Each option has a
 * glyph AND an accessible label — never icon-only without a name.
 */

import { Monitor, Moon, Sun } from "lucide-react";

import { useTheme } from "@/lib/use-theme";
import { cn } from "@/lib/utils";
import type { ThemeChoice } from "@/lib/theme";

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function ThemeToggle() {
  const { choice, setChoice } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      data-testid="theme-toggle"
      className="inline-flex items-center rounded-md border border-border bg-background p-0.5"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = choice === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setChoice(value)}
            data-testid={`theme-${value}`}
            className={cn(
              "inline-flex h-6 w-6 items-center justify-center rounded-sm transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
