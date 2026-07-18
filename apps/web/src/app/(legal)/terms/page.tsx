import type { Metadata } from "next";

import { Clause, LegalPage } from "../_components/legal-page";

export const metadata: Metadata = {
  title: "Terms of Service — DM Tool",
  description: "The terms governing use of DM Tool.",
  robots: { index: true, follow: true },
};

// Standard SaaS Terms-of-Service section structure. Placeholders only — no
// binding promise is authored here; each clause must be replaced with
// lawyer-approved text before launch.
export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service" updated="TODO: effective date">
      <p>
        These Terms of Service (&ldquo;Terms&rdquo;) govern access to and use of
        DM Tool (the &ldquo;Service&rdquo;). Placeholder introduction — describe
        who the provider is and that using the Service means accepting these
        Terms. TODO: Replace with lawyer-approved text.
      </p>

      <Clause heading="1. Accounts and eligibility">
        <p>Who may register, account responsibility, and accurate information.</p>
      </Clause>
      <Clause heading="2. Subscriptions, billing, and refunds">
        <p>
          Plans, billing cycle, taxes, auto-renewal, cancellation, and refund
          policy (align with the Stripe billing flow).
        </p>
      </Clause>
      <Clause heading="3. Acceptable use">
        <p>
          Prohibited conduct, content restrictions, and consequences of misuse.
        </p>
      </Clause>
      <Clause heading="4. Customer content and ownership">
        <p>
          Ownership of content the customer provides and content the Service
          generates, and the license granted to operate the Service.
        </p>
      </Clause>
      <Clause heading="5. AI-generated output">
        <p>
          Nature of AI output, no guarantee of accuracy, and customer
          responsibility for reviewing and approving generated marketing before
          publishing.
        </p>
      </Clause>
      <Clause heading="6. Third-party services and integrations">
        <p>
          Connected platforms (social, email, payment) are governed by their own
          terms; the Service is not responsible for them.
        </p>
      </Clause>
      <Clause heading="7. Intellectual property">
        <p>Ownership of the Service, trademarks, and feedback license.</p>
      </Clause>
      <Clause heading="8. Warranties and disclaimers">
        <p>Service provided &ldquo;as is&rdquo; and disclaimer scope.</p>
      </Clause>
      <Clause heading="9. Limitation of liability">
        <p>Liability cap and excluded damages.</p>
      </Clause>
      <Clause heading="10. Indemnification">
        <p>Customer indemnity obligations.</p>
      </Clause>
      <Clause heading="11. Termination">
        <p>Suspension, termination, and effect of termination.</p>
      </Clause>
      <Clause heading="12. Governing law and disputes">
        <p>Governing jurisdiction and dispute-resolution mechanism.</p>
      </Clause>
      <Clause heading="13. Changes to these Terms">
        <p>How and when Terms may change and notice given.</p>
      </Clause>
      <Clause heading="14. Contact">
        <p>Legal/support contact details. TODO: add real contact address.</p>
      </Clause>
    </LegalPage>
  );
}
