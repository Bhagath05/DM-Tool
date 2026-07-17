"use client";

/**
 * Shared Brand Brain field editors.
 *
 * Used by both the Brand Brain page and the AI discovery review step so the
 * two surfaces edit brand knowledge with identical affordances — one
 * implementation, no duplicate components.
 */

import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type IconType = React.ComponentType<{ className?: string }>;

export function Field({
  label,
  value,
  editing,
  multiline,
  hint,
  children,
}: {
  label: string;
  value: string;
  editing: boolean;
  multiline?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {hint && editing && (
          <span className="text-[11px] text-muted-foreground/70">{hint}</span>
        )}
      </div>
      {editing ? (
        children
      ) : value ? (
        <p className={cn("text-sm", multiline && "whitespace-pre-wrap")}>{value}</p>
      ) : (
        <p className="text-sm italic text-muted-foreground/60">Not set yet</p>
      )}
    </div>
  );
}

export function ChipsField({
  label,
  values,
  editing,
  onChange,
  placeholder,
  icon: Icon,
}: {
  label: string;
  values: string[];
  editing: boolean;
  onChange: (v: string[]) => void;
  placeholder?: string;
  icon?: IconType;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput("");
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {values.length === 0 && !editing ? (
        <p className="text-sm italic text-muted-foreground/60">Not set yet</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs"
            >
              {Icon && <Icon className="h-3 w-3 text-muted-foreground" />}
              {v}
              {editing && (
                <button
                  type="button"
                  onClick={() => onChange(values.filter((x) => x !== v))}
                  aria-label={`Remove ${v}`}
                  className="text-muted-foreground hover:text-bad-soft-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {editing && (
        <div className="mt-1 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder={placeholder}
            className="h-8 text-sm"
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={add}
            disabled={!input.trim()}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}

export function ColorsField({
  label,
  values,
  editing,
  onChange,
}: {
  label: string;
  values: string[];
  editing: boolean;
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("#");
  const add = () => {
    const v = input.trim();
    if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v) && !values.includes(v)) {
      onChange([...values, v]);
    }
    setInput("#");
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {values.length === 0 && !editing ? (
        <p className="text-sm italic text-muted-foreground/60">Not set yet</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {values.map((c) => (
            <span
              key={c}
              className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 text-xs"
            >
              <span
                className="h-4 w-4 rounded-full border border-border"
                style={{ backgroundColor: c }}
                aria-hidden
              />
              <span className="font-mono">{c}</span>
              {editing && (
                <button
                  type="button"
                  onClick={() => onChange(values.filter((x) => x !== c))}
                  aria-label={`Remove ${c}`}
                  className="text-muted-foreground hover:text-bad-soft-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {editing && (
        <div className="mt-1 flex items-center gap-2">
          <input
            type="color"
            value={/^#([0-9a-fA-F]{6})$/.test(input) ? input : "#000000"}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Pick colour"
            className="h-8 w-10 cursor-pointer rounded border border-input bg-background"
          />
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder="#8B4513"
            className="h-8 w-28 font-mono text-sm"
          />
          <Button type="button" size="sm" variant="outline" onClick={add}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
