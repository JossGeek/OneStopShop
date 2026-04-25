import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmResult, ImportInvalidRow, ImportValidRow, PreviewResult } from '../shared/api.models';
import { OssApiService } from '../shared/oss-api.service';

type PageState = 'upload' | 'preview' | 'result';

@Component({
  selector: 'app-import-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './import-page.component.html',
  styleUrls: ['./import-page.component.css'],
})
export class ImportPageComponent {
  private readonly api = inject(OssApiService);
  private readonly http = inject(HttpClient);

  state = signal<PageState>('upload');

  // Upload state
  selectedFile: File | null = null;
  uploading = signal(false);
  uploadError = signal<string | null>(null);

  // Preview state
  validRows: ImportValidRow[] = [];
  invalidRows: ImportInvalidRow[] = [];
  selectedRows = new Set<number>();

  // Result state
  confirmResult: ConfirmResult | null = null;
  confirming = signal(false);
  confirmError = signal<string | null>(null);

  get allSelected(): boolean {
    return this.validRows.length > 0 && this.selectedRows.size === this.validRows.length;
  }

  get someSelected(): boolean {
    return this.selectedRows.size > 0 && !this.allSelected;
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
    this.uploadError.set(null);
  }

  onPreview(): void {
    if (!this.selectedFile) return;
    this.uploading.set(true);
    this.uploadError.set(null);

    this.api.previewImport(this.selectedFile).subscribe({
      next: (result: PreviewResult) => {
        this.uploading.set(false);
        this.validRows = result.valid;
        this.invalidRows = result.invalid;
        this.selectedRows = new Set(result.valid.map((r) => r.row));
        this.state.set('preview');
      },
      error: (err) => {
        this.uploading.set(false);
        this.uploadError.set(err?.error?.error ?? 'Failed to parse file. Check format and try again.');
      },
    });
  }

  toggleRow(row: number): void {
    if (this.selectedRows.has(row)) {
      this.selectedRows.delete(row);
    } else {
      this.selectedRows.add(row);
    }
    // Force change detection for Set mutation
    this.selectedRows = new Set(this.selectedRows);
  }

  toggleAll(): void {
    if (this.allSelected) {
      this.selectedRows = new Set();
    } else {
      this.selectedRows = new Set(this.validRows.map((r) => r.row));
    }
  }

  isSelected(row: number): boolean {
    return this.selectedRows.has(row);
  }

  onConfirm(publish: boolean): void {
    const rows = this.validRows.filter((r) => this.selectedRows.has(r.row));
    if (rows.length === 0) return;

    this.confirming.set(true);
    this.confirmError.set(null);

    this.api.confirmImport(rows, publish).subscribe({
      next: (result: ConfirmResult) => {
        this.confirming.set(false);
        this.confirmResult = result;
        this.state.set('result');
      },
      error: (err) => {
        this.confirming.set(false);
        this.confirmError.set(err?.error?.error ?? 'Import failed. Please try again.');
      },
    });
  }

  onDownloadTemplate(): void {
    this.api.getImportTemplate();
  }

  onBack(): void {
    this.state.set('upload');
    this.selectedFile = null;
    this.uploadError.set(null);
  }

  onReset(): void {
    this.state.set('upload');
    this.selectedFile = null;
    this.validRows = [];
    this.invalidRows = [];
    this.selectedRows = new Set();
    this.confirmResult = null;
    this.uploadError.set(null);
    this.confirmError.set(null);
  }

  rowDataPreview(row: ImportValidRow | ImportInvalidRow): string {
    const d = row.data;
    return [d['title'] || d['url'] || '', d['organization'] || '', d['offer_type'] || '']
      .filter(Boolean)
      .join(' · ');
  }
}
