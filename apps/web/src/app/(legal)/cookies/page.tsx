import type { Metadata } from "next";

import { Clause, LegalPage } from "../_components/legal-page";

export const metadata: Metadata = {
  title: "Cookie Policy — DM Tool",
  description: "How DM Tool uses cookies and similar technologies.",
  robots: { index: true, follow: true },
};

// Cookie Policy scaffolding. The actual cookie inventory must be generated
// from the real deployed app (auth, analytics, preferences) and approved.
export default function CookiesPage() {
  return (
    <LegalPage title="Cookie Policy" updated="TODO: effective date">
      <p>
        This Cookie Policy explains how DM Tool uses cookies and similar
        technologies. Placeholder introduction. TODO: Replace with
        lawyer-approved text.
      </p>

      <Clause heading="1. What cookies are">
        <p>Plain-language explanation of cookies and similar technologies.</p>
      </Clause>
      <Clause heading="2. Cookies we use">
        <p>
          Categorised inventory — strictly necessary (authentication/session),
          preferences, and analytics — with purpose and duration for each. TODO:
          generate the real cookie inventory from the deployed app.
        </p>
      </Clause>
      <Clause heading="3. Third-party cookies">
        <p>
          Cookies set by integrated services (authentication, payment,
          analytics).
        </p>
      </Clause>
      <Clause heading="4. Managing cookies">
        <p>
          How to accept, reject, or change cookie choices, and browser controls.
          TODO: wire this to the cookie-consent banner (Wave 1).
        </p>
      </Clause>
      <Clause heading="5. Changes and contact">
        <p>How changes are communicated and the contact address.</p>
      </Clause>
    </LegalPage>
  );
}
