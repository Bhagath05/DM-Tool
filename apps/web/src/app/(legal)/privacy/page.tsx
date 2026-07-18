import type { Metadata } from "next";

import { Clause, LegalPage } from "../_components/legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy — DM Tool",
  description: "How DM Tool collects, uses, and protects personal data.",
  robots: { index: true, follow: true },
};

// GDPR/CCPA-shaped Privacy Policy section structure. Placeholders only — the
// specific data practices, legal bases, retention periods, and subprocessor
// list must be filled in and approved by counsel.
export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="TODO: effective date">
      <p>
        This Privacy Policy explains how DM Tool collects, uses, discloses, and
        protects personal data, and the rights available to individuals.
        Placeholder introduction. TODO: Replace with lawyer-approved text.
      </p>

      <Clause heading="1. Who we are (data controller)">
        <p>Legal entity, address, and contact for privacy enquiries.</p>
      </Clause>
      <Clause heading="2. Data we collect">
        <p>
          Account data, business-profile / Brand Brain data, generated content,
          usage data, and payment data (handled by the payment processor).
        </p>
      </Clause>
      <Clause heading="3. How we use data and legal bases">
        <p>
          Purposes of processing and the legal basis for each (contract,
          legitimate interest, consent) under GDPR.
        </p>
      </Clause>
      <Clause heading="4. AI processing">
        <p>
          What data is sent to AI providers to generate marketing, and that
          content is not used to train third-party models beyond what those
          providers&rsquo; terms allow.
        </p>
      </Clause>
      <Clause heading="5. Subprocessors and third parties">
        <p>
          List of subprocessors (hosting, AI, payment, email, error monitoring)
          and links to their terms. TODO: maintain an accurate subprocessor list.
        </p>
      </Clause>
      <Clause heading="6. International transfers">
        <p>Transfer mechanisms (e.g. SCCs) where data leaves its region.</p>
      </Clause>
      <Clause heading="7. Data retention">
        <p>How long each category of data is kept and deletion on request.</p>
      </Clause>
      <Clause heading="8. Your rights">
        <p>
          Access, rectification, erasure, portability, objection, and how to
          exercise them (the Service supports workspace data export and
          deletion).
        </p>
      </Clause>
      <Clause heading="9. Security">
        <p>
          Encryption in transit and at rest, access controls, and breach
          notification.
        </p>
      </Clause>
      <Clause heading="10. Cookies">
        <p>
          Reference the{" "}
          <a href="/cookies" className="underline hover:text-foreground">
            Cookie Policy
          </a>
          .
        </p>
      </Clause>
      <Clause heading="11. Children">
        <p>Minimum age and no intentional collection from minors.</p>
      </Clause>
      <Clause heading="12. Changes and contact">
        <p>How changes are communicated and the privacy contact address.</p>
      </Clause>
    </LegalPage>
  );
}
