export interface OfferTypeLookup {
  id: string;
  name: string;
  description: string;
}

export interface DomainLookup {
  id: string;
  name: string;
}

export interface OrganizationLookup {
  id: string;
  name: string;
  type: string;
  country: string;
}

export interface CountryLookup {
  code: string;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  type: string;
  country: string;
}

export interface Offer {
  id: string;
  title: string;
  summary: string;
  link: string;
  country: string;
  status: string;
  offer_type: string;
  organization: OrganizationSummary;
  source_type: string;
  target_profile: string;
  domains: string[];
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface OfferListResponse {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  limit: number;
  results: Offer[];
}

export interface ScrapingRunSummary {
  id: string;
  source_key: string;
  status: string;
  job: string | null;
  offers_processed: number;
  offers_created: number;
  offers_updated: number;
  offers_unchanged: number;
  offers_flagged_stale: number;
  errors_count: number;
  llm_calls_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ScrapingRunListResponse {
  count: number;
  results: ScrapingRunSummary[];
}

export interface ScrapingRunDetail extends ScrapingRunSummary {
  offers_deleted: number;
  log: Array<Record<string, unknown>>;
  updated_at: string;
}

export interface LookupResponse<T> {
  count: number;
  results: T[];
}

export interface OfferQueryParams {
  q?: string;
  status?: string;
  offer_type?: string;
  organization?: string;
  target_profile?: string;
  domain?: string;
  country?: string;
  page?: number;
  page_size?: number;
  limit?: number;
}
