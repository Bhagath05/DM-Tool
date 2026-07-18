/**
 * Public layout for legal pages. No app chrome, no auth required — these must
 * be reachable by anyone (regulators, prospects, linked from sign-up).
 */

export default function LegalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-10 sm:py-16">
      {children}
    </main>
  );
}
