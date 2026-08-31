/**
 * Clerk `appearance` mapped onto DM Tool's design tokens so the built-in
 * <SignIn>/<SignUp> widgets look native to the product — without replacing
 * Clerk or building custom auth forms. Clerk keeps ownership of the actual
 * flows (sign-in, sign-up, forgot-password, reset, social/Google, session).
 *
 * Colors reference the Tailwind v4 `@theme` CSS variables from globals.css, so
 * the widget follows light/dark automatically. We neutralize Clerk's outer card
 * chrome so the widget sits inside our own branded panel, but leave the header,
 * footer, "Forgot password?", and social buttons intact.
 */
// Typed structurally (not via @clerk/types) so this file never depends on a
// transitive package export. The shape is validated where it's passed to
// <SignIn appearance={...}> / <SignUp appearance={...}>.
export const clerkAppearance = {
  variables: {
    colorPrimary: "var(--color-primary)",
    colorText: "var(--color-foreground)",
    colorTextSecondary: "var(--color-muted-foreground)",
    colorBackground: "var(--color-card)",
    colorInputBackground: "var(--color-background)",
    colorInputText: "var(--color-foreground)",
    colorDanger: "var(--color-bad, hsl(0 72% 51%))",
    borderRadius: "var(--radius-md, 0.625rem)",
    fontFamily: "inherit",
  },
  elements: {
    // Let our AuthShell panel provide the card chrome; keep the form itself.
    rootBox: "w-full",
    cardBox: "w-full shadow-none",
    card: "shadow-none border-0 bg-transparent p-0",
    // Our shell renders the title/subtitle, so hide Clerk's duplicate header.
    header: "hidden",
    footer:
      "[&_.cl-footerActionLink]:text-primary [&_.cl-footerActionLink]:font-medium",
    socialButtonsBlockButton:
      "border-border hover:bg-muted transition-colors",
    formButtonPrimary:
      "bg-primary text-primary-foreground hover:opacity-90 transition-opacity",
    formFieldInput: "border-border",
  },
};
