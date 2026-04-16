import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  CountryLookup,
  DomainLookup,
  LookupResponse,
  OfferListResponse,
  OfferQueryParams,
  OrganizationLookup,
  OfferTypeLookup,
  ScrapingRunDetail,
  ScrapingRunListResponse,
} from './api.models';

@Injectable({
  providedIn: 'root',
})
export class OssApiService {
  private readonly apiBaseUrl = 'http://localhost:8000/api';

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
