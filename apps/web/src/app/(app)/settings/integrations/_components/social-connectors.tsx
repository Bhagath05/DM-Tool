"use client";

import { InstagramConnector } from "./instagram-connector";
import { IntegrationConnector } from "./integration-connector";
import {
  MarkFacebook,
  MarkGoogle,
  MarkLinkedIn,
  MarkPinterest,
  MarkYouTube,
} from "./platform-marks";

const SOCIAL_CONNECTORS = [
  {
    slug: "facebook_pages",
    title: "Facebook",
    description:
      "Connect a Facebook Page to publish posts and sync page engagement metrics.",
    testId: "integration-facebook",
    mark: <MarkFacebook />,
    envHint:
      "Set FB_CLIENT_ID and FB_CLIENT_SECRET (or reuse IG_CLIENT_* Meta app credentials).",
  },
  {
    slug: "linkedin_organic",
    title: "LinkedIn",
    description:
      "Publish to your company page and sync follower and engagement signals.",
    testId: "integration-linkedin",
    mark: <MarkLinkedIn />,
    envHint: "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET on the API server.",
  },
  {
    slug: "youtube",
    title: "YouTube",
    description:
      "Connect your channel to publish videos and sync subscriber and view counts.",
    testId: "integration-youtube",
    mark: <MarkYouTube />,
    envHint: "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET on the API server.",
  },
  {
    slug: "pinterest",
    title: "Pinterest",
    description:
      "Publish pins to your boards and sync account-level engagement metrics.",
    testId: "integration-pinterest",
    mark: <MarkPinterest />,
    envHint: "Set PINTEREST_APP_ID and PINTEREST_APP_SECRET on the API server.",
  },
] as const;

export function SocialPublishingConnectors() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <InstagramConnector />
      {SOCIAL_CONNECTORS.map((c) => (
        <IntegrationConnector key={c.slug} {...c} />
      ))}
      <IntegrationConnector
        slug="google_business_profile"
        title="Google Business Profile"
        description="Pull reviews, calls, directions, website clicks, and profile views."
        testId="integration-google-business-profile"
        mark={<MarkGoogle />}
        envHint="Set GOOGLE_GBP_CLIENT_ID and GOOGLE_GBP_CLIENT_SECRET on the API server."
      />
    </div>
  );
}
