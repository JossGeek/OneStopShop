import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject, forkJoin, takeUntil } from 'rxjs';
import {
  CountryLookup,
  DomainLookup,
  Offer,
  OfferQueryParams,
  OfferTypeLookup,
  OrganizationLookup,
} from '../shared/api.models';
import { OssApiService } from '../shared/oss-api.service';

@Component({
  selector: 'app-offers-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './offers-page.component.html',
  styleUrl: './offers-page.component.css',
})
export class OffersPageComponent implements OnInit, OnDestroy {
  readonly statuses = ['draft', 'published', 'archived'];
  readonly targetProfiles = ['student', 'researcher', 'company'];
  readonly pageSizeOptions = [6, 12, 24, 50];

  offerTypes: OfferTypeLookup[] = [];
  domains: DomainLookup[] = [];
  organizations: OrganizationLookup[] = [];
  countries: CountryLookup[] = [];
  offers: Offer[] = [];

  q = '';
  status = '';
  offerType = '';
  organization = '';
  targetProfile = '';
  domain = '';
  country = '';

  page = 1;
  pageSize = 12;
  totalPages = 0;
  totalCount = 0;

  loading = false;
  loadingLookups = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly api: OssApiService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadLookups();

    this.route.queryParamMap
      .pipe(takeUntil(this.destroy$))
      .subscribe((params) => {
        this.q = params.get('q') ?? '';
        this.status = params.get('status') ?? '';
        this.offerType = params.get('offer_type') ?? '';
        this.organization = params.get('organization') ?? '';
        this.targetProfile = params.get('target_profile') ?? '';
        this.domain = params.get('domain') ?? '';
        this.country = params.get('country') ?? '';

        this.page = this.toPositiveInt(params.get('page'), 1);
        this.pageSize = this.toPositiveInt(
          params.get('page_size') ?? params.get('limit'),
          12,
        );

        this.fetchOffers();
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onApplyFilters(): void {
    this.navigateWithQuery({
      q: this.q,
      status: this.status,
      offer_type: this.offerType,
      organization: this.organization,
      target_profile: this.targetProfile,
      domain: this.domain,
      country: this.country.toUpperCase(),
      page: 1,
      page_size: this.pageSize,
    });
  }

  onResetFilters(): void {
    this.q = '';
    this.status = '';
    this.offerType = '';
    this.organization = '';
    this.targetProfile = '';
    this.domain = '';
    this.country = '';

    this.navigateWithQuery({
      page: 1,
      page_size: this.pageSize,
    });
  }

  onPageSizeChange(): void {
    this.navigateWithQuery({
      q: this.q,
      status: this.status,
      offer_type: this.offerType,
      organization: this.organization,
      target_profile: this.targetProfile,
      domain: this.domain,
      country: this.country.toUpperCase(),
      page: 1,
      page_size: this.pageSize,
    });
  }

  onPageChange(nextPage: number): void {
    if (nextPage < 1 || (this.totalPages > 0 && nextPage > this.totalPages)) {
      return;
    }

    this.navigateWithQuery({
      q: this.q,
      status: this.status,
      offer_type: this.offerType,
      organization: this.organization,
      target_profile: this.targetProfile,
      domain: this.domain,
      country: this.country.toUpperCase(),
      page: nextPage,
      page_size: this.pageSize,
    });
  }

  pageNumbers(): number[] {
    if (this.totalPages <= 1) {
      return this.totalPages === 1 ? [1] : [];
    }

    const spread = 2;
    const start = Math.max(1, this.page - spread);
    const end = Math.min(this.totalPages, this.page + spread);
    const pages: number[] = [];

    for (let index = start; index <= end; index += 1) {
      pages.push(index);
    }

    return pages;
  }

  trackOffer(_index: number, offer: Offer): string {
    return offer.id;
  }

  private fetchOffers(): void {
    this.loading = true;
    this.errorMessage = '';

    const query: OfferQueryParams = {
      q: this.q,
      status: this.status,
      offer_type: this.offerType,
      organization: this.organization,
      target_profile: this.targetProfile,
      domain: this.domain,
      country: this.country,
      page: this.page,
      page_size: this.pageSize,
    };

    this.api
      .getOffers(query)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (payload) => {
          this.offers = payload.results;
          this.totalCount = payload.count;
          this.page = payload.page;
          this.pageSize = payload.page_size;
          this.totalPages = payload.total_pages;
          this.loading = false;
        },
        error: () => {
          this.errorMessage = 'Could not load offers. Verify that the API is reachable at localhost:8000.';
          this.loading = false;
        },
      });
  }

  private loadLookups(): void {
    this.loadingLookups = true;

    forkJoin({
      offerTypes: this.api.getOfferTypes(),
      domains: this.api.getDomains(),
      organizations: this.api.getOrganizations(),
      countries: this.api.getCountries(),
    })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ({ offerTypes, domains, organizations, countries }) => {
          this.offerTypes = offerTypes.results;
          this.domains = domains.results;
          this.organizations = organizations.results;
          this.countries = countries.results;
          this.loadingLookups = false;
        },
        error: () => {
          this.loadingLookups = false;
        },
      });
  }

  private navigateWithQuery(query: OfferQueryParams): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: query,
    });
  }

  private toPositiveInt(value: string | null, fallback: number): number {
    if (!value) {
      return fallback;
    }

    const parsed = Number.parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < 1) {
      return fallback;
    }

    return parsed;
  }
}
