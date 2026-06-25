import { notFound } from "next/navigation";

import { api } from "@/lib/api";

import { LandingPageView } from "./landing-page-view";

export const dynamic = "force-dynamic";
export const revalidate = 60; // edge-cache landing pages for 1 minute

type SearchParams = {
  preview?: string;
  src?: string;
  id?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_term?: string;
  utm_content?: string;
};

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { slug } = await params;
  const search = await searchParams;

  let page;
  try {
    page = await api.landingPages.getPublic(slug, search.preview);
  } catch {
    notFound();
  }

  // Attribution from URL — flow into the lead record on submit
  const attribution = {
    source_asset_type: search.src ?? "direct",
    source_asset_id: search.id ?? null,
    utm_source: search.utm_source ?? null,
    utm_medium: search.utm_medium ?? null,
    utm_campaign: search.utm_campaign ?? null,
    utm_term: search.utm_term ?? null,
    utm_content: search.utm_content ?? null,
  };

  return (
    <LandingPageView
      slug={slug}
      page={page}
      attribution={attribution}
      isPreview={Boolean(search.preview)}
    />
  );
}
