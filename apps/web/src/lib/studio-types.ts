/**
 * Creative Studio (CS1) frontend types — mirror the backend's closed layer
 * schema + design/revision shapes. Read-only for CS1 (the viewer + history);
 * the editor (Pro Mode) lands in CS5.
 */

export type LayerType =
  | "text"
  | "image"
  | "icon"
  | "shape"
  | "video"
  | "audio"
  | "group";

export type LayerRole =
  | "background"
  | "logo"
  | "headline"
  | "subhead"
  | "body"
  | "cta"
  | "product"
  | "decoration"
  | "subtitle";

export interface DesignLayer {
  type: LayerType;
  id: string;
  role?: LayerRole | null;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  rotation?: number;
  opacity?: number;
  z?: number;
  locked?: boolean;
  // text
  text?: string;
  color?: string;
  font_family?: string;
  font_size?: number;
  align?: "left" | "center" | "right" | "justify";
  weight?: "regular" | "medium" | "semibold" | "bold";
  // shape
  shape?: "rect" | "ellipse" | "line";
  fill?: string | null;
  radius?: number;
  // icon
  icon_name?: string;
  // image/video/audio
  asset_id?: string;
  fit?: "cover" | "contain" | "fill" | "stretch";
  crop?: { x: number; y: number; w: number; h: number };
  mask?: { kind: "none" | "circle" | "rounded_rect"; radius?: number };
  // group
  children?: DesignLayer[];
}

export interface DesignBackground {
  kind: "color" | "image" | "none";
  color?: string;
  asset_id?: string | null;
}

export interface DesignPage {
  background: DesignBackground;
  layers: DesignLayer[];
  duration_ms?: number | null;
}

export interface DesignDoc {
  version: number;
  format_slug?: string | null;
  aspect?: string | null;
  pages: DesignPage[];
}

export interface DesignSummary {
  id: string;
  name: string;
  media_type: string;
  format_slug?: string | null;
  current_revision: number;
  default_mode: string;
  status: string;
  updated_at: string;
}

export interface DesignResponse {
  id: string;
  name: string;
  media_type: string;
  format_slug?: string | null;
  growth_objective_id?: string | null;
  current_revision: number;
  head_revision_id?: string | null;
  default_mode: string;
  status: string;
  doc: DesignDoc;
  created_at: string;
  updated_at: string;
}

export type RevisionSource =
  | "ai_generate"
  | "ai_edit"
  | "ai_regenerate"
  | "ai_restyle"
  | "ai_transform"
  | "user_edit"
  | "template";

export interface RevisionSummary {
  id: string;
  revision_n: number;
  parent_revision_id?: string | null;
  source: RevisionSource;
  actor_kind: "ai" | "human";
  mode: "ai" | "guided" | "pro";
  review_status: string;
  created_by_user_id?: string | null;
  edit_summary?: string | null;
  created_at: string;
}

export interface ObjectiveKind {
  slug: string;
  display_name: string;
  category: string;
  kpi_hint?: string | null;
  default_channels: string[];
}

export interface GrowthObjective {
  id: string;
  objective_kind: string;
  statement: string;
  audience_hypothesis?: string | null;
  budget_cents?: number | null;
  status: string;
  created_at: string;
}

export interface CampaignStrategyOut {
  objective_summary: string;
  audience: string;
  hook: string;
  value_prop: string;
  proof_point?: string | null;
  cta_angle: string;
  channels: string[];
}

export interface BuiltAsset {
  design_id: string;
  name: string;
  creative_type: string;
  media_type: string;
  aspect: string;
  current_revision: number;
  rationale?: string | null;
}

export interface CampaignBuildResponse {
  objective_id: string;
  strategy: CampaignStrategyOut;
  assets: BuiltAsset[];
}

export interface BrandAsset {
  id: string;
  kind: "logo" | "font" | "image" | "color" | "icon";
  label?: string | null;
  mime_type?: string | null;
  is_favorite: boolean;
  url?: string | null;
  created_at: string;
}

export interface StockResult {
  provider: string;
  external_id: string;
  label: string;
  thumb_url: string;
  full_url: string;
}

export interface VideoRenderResponse {
  design_id: string;
  project_id: string;
  status: string;
}

export interface VideoStatus {
  design_id: string;
  project_id?: string | null;
  status: string;
  asset_id?: string | null;
  video_url?: string | null;
  captions_url?: string | null;
  duration_ms?: number | null;
  scenes?: number | null;
}

export interface VideoExport {
  id: string;
  target_platform?: string | null;
  format_slug?: string | null;
  width?: number | null;
  height?: number | null;
  status: string;
}

export interface NlEditResponse {
  op_class: "edit" | "regenerate" | "transform" | "restyle" | "variant";
  confidence: number;
  summary: string;
  committed: boolean;
  design_id: string;
  current_revision: number;
  proposed_doc?: DesignDoc | null;
  created_design_ids: string[];
  notes?: string | null;
}
