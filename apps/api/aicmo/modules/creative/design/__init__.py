"""Creative Studio design subsystem (CS1).

The editable layer document is the source of truth (Editability Invariant);
the rendered file is an output cache. Three modes — AI / Guided / Pro —
operate on the SAME `creative_design` through ONE write path
(`apply_revision`); nothing mutates a design in place (Law 3). Every change
appends an immutable `creative_design_revision`.
"""
