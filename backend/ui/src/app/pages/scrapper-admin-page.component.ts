import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import { ScrapingRunDetail, ScrapingRunSummary } from '../shared/api.models';
import { OssApiService } from '../shared/oss-api.service';

@Component({
  selector: 'app-scrapper-admin-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './scrapper-admin-page.component.html',
  styleUrl: './scrapper-admin-page.component.css',
})
export class ScrapperAdminPageComponent implements OnInit, OnDestroy {
  runs: ScrapingRunSummary[] = [];
  selectedRun: ScrapingRunDetail | null = null;

  limit = 20;
  sourceFilter = '';
  statusFilter = '';

  loadingRuns = false;
  loadingDetail = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(private readonly api: OssApiService) {}

  ngOnInit(): void {
    this.refreshRuns();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get filteredRuns(): ScrapingRunSummary[] {
    return this.runs.filter((run) => {
      const statusMatches = this.statusFilter ? run.status === this.statusFilter : true;
      const sourceMatches = this.sourceFilter
        ? run.source_key.toLowerCase().includes(this.sourceFilter.toLowerCase())
        : true;
      return statusMatches && sourceMatches;
    });
  }

  get statuses(): string[] {
    return Array.from(new Set(this.runs.map((run) => run.status))).sort();
  }

  refreshRuns(): void {
    this.loadingRuns = true;
    this.errorMessage = '';

    this.api
      .getScrapingRuns(this.limit)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (payload) => {
          this.runs = payload.results;
          this.loadingRuns = false;

          if (!this.selectedRun && this.runs.length > 0) {
            this.selectRun(this.runs[0].id);
          }
        },
        error: () => {
          this.errorMessage = 'Could not load scraping runs. Verify API connectivity.';
          this.loadingRuns = false;
        },
      });
  }

  selectRun(runId: string): void {
    this.loadingDetail = true;

    this.api
      .getScrapingRunDetail(runId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (payload) => {
          this.selectedRun = payload;
          this.loadingDetail = false;
        },
        error: () => {
          this.selectedRun = null;
          this.loadingDetail = false;
        },
      });
  }

  trackRun(_index: number, run: ScrapingRunSummary): string {
    return run.id;
  }
}
