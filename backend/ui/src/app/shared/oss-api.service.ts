import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  ConfirmResult,
  CountryLookup,
  DomainLookup,
  ImportValidRow,
  LlmStats,
  LookupResponse,
  OfferListResponse,
  OfferQueryParams,
  OrganizationLookup,
  OfferTypeLookup,
  PreviewResult,
  ScrapingOverview,
  ScrapingRunDetail,
  ScrapingRunListResponse,
  SourcesHealthResponse,
} from './api.models';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class OssApiService {
  private readonly apiBaseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  getOfferTypes(): Observable<LookupResponse<OfferTypeLookup>> {
    return this.http.get<LookupResponse<OfferTypeLookup>>(`${this.apiBaseUrl}/lookups/offer-types`);
  }

  getDomains(): Observable<LookupResponse<DomainLookup>> {
    return this.http.get<LookupResponse<DomainLookup>>(`${this.apiBaseUrl}/lookups/domains`);
  }

  getOrganizations(): Observable<LookupResponse<OrganizationLookup>> {
    return this.http.get<LookupResponse<OrganizationLookup>>(`${this.apiBaseUrl}/lookups/organizations`);
  }

  getCountries(): Observable<LookupResponse<CountryLookup>> {
    return this.http.get<LookupResponse<CountryLookup>>(`${this.apiBaseUrl}/lookups/countries`);
  }

  getOffers(query: OfferQueryParams): Observable<OfferListResponse> {
    return this.http.get<OfferListResponse>(`${this.apiBaseUrl}/offers`, {
      params: this.buildParams(query),
    });
  }

  getScrapingRuns(limit = 20): Observable<ScrapingRunListResponse> {
    return this.http.get<ScrapingRunListResponse>(`${this.apiBaseUrl}/scraping/runs`, {
      params: this.buildParams({ limit }),
    });
  }

  getScrapingRunDetail(runId: string): Observable<ScrapingRunDetail> {
    return this.http.get<ScrapingRunDetail>(`${this.apiBaseUrl}/scraping/runs/${runId}`);
  }

  getScrapingOverview(window: '24h' | '7d' | '30d' = '24h'): Observable<ScrapingOverview> {
    return this.http.get<ScrapingOverview>(`${this.apiBaseUrl}/scraping/overview`, {
      params: this.buildParams({ window }),
    });
  }

  getSourcesHealth(): Observable<SourcesHealthResponse> {
    return this.http.get<SourcesHealthResponse>(`${this.apiBaseUrl}/scraping/sources/health`);
  }

  getLlmStats(window: '24h' | '7d' | '30d' = '24h'): Observable<LlmStats> {
    return this.http.get<LlmStats>(`${this.apiBaseUrl}/scraping/llm/stats`, {
      params: this.buildParams({ window }),
    });
  }

  previewImport(file: File): Observable<PreviewResult> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<PreviewResult>(`${this.apiBaseUrl}/offers/import/preview`, form);
  }

  confirmImport(rows: ImportValidRow[], publish: boolean): Observable<ConfirmResult> {
    return this.http.post<ConfirmResult>(`${this.apiBaseUrl}/offers/import/confirm`, { rows, publish });
  }

  getImportTemplate(): void {
    window.open(`${this.apiBaseUrl}/offers/import/template`, '_blank');
  }

  private buildParams(
    query: OfferQueryParams | Record<string, string | number | undefined>,
  ): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === '') {
        continue;
      }
      params = params.set(key, String(value));
    }
    return params;
  }
}
