// pop up for uploading a page
// task u-3

import { Component, ElementRef, inject, signal, viewChild } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { DecimalPipe } from "@angular/common";
import { ApiService } from "../api.service";
import { IngestResponse } from "../models";

@Component({
    selector: 'app-upload-dialog',
    imports: [FormsModule, DecimalPipe],
    template: `
    <dialog #dlg class="upload-dialog" (close)="reset()" aria-labelledby="upload-title">
      <form class="upload-form" (ngSubmit)="upload()">
        <h2 id="upload-title">upload a page</h2>
        <p class="hint">pick a .txt, .pdf, or .docx docs page, it gets chunked, embedded and added to the vector db</p>

        <label class="field">
          File
          <input #fileInput type="file" accept=".txt,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" (change)="pick($event)" />
        </label>

        <!-- this is optional, but if left blank, the backend uses the file's own header / file name -->
        <label class="field">
          Title
          <input name="title" [(ngModel)]="title" placeholder="e.g. Idle and physics processing" />
        </label>
        <label class="field">
          Section
          <input name="section" [(ngModel)]="section" placeholder="e.g. Scripting" />
        </label>
        <label class="field">
          Docs URL
          <input name="url" type="url" [(ngModel)]="url" placeholder="https://docs.godotengine.org/..." />
        </label>

        @if (error()) {
          <p class="error" role="alert">{{ error() }}</p>
        }

        <!-- success message: the part the audience sees in the demo -->
        @if (result(); as r) {
          <div class="upload-result" role="status">
            ✔️ added <b>{{ r.chunks_added }}</b> chunks from <b>{{ r.title }}</b>
            @if (r.took_ms != null) { in {{ r.took_ms / 1000 | number: '1.2-2' }} s }.
            @if (r.total_chunks != null) {
              <br />the database now holds <b>{{ r.total_chunks }}</b> chunks, try searching for it!
            }
          </div>
        }

        <div class="dialog-actions">
          <button type="button" class="btn-secondary" (click)="close()">
            {{ result() ? 'Done' : 'Cancel' }}
          </button>
          <button type="submit" class="btn-primary" [disabled]="!file || loading()">
            {{ loading() ? 'Uploading…' : 'Upload' }}
          </button>
        </div>
      </form>
    </dialog>
  `,
})

export class UploadDialogComponent {
    private api = inject(ApiService);
    private dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');
    private fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');

    file: File | null = null;    // chosen file
    title = '';
    section = '';
    url = '';

    loading = signal(false);
    error = signal<string | null>(null);
    result = signal<IngestResponse | null>(null);

    open() {
        this.dlg().nativeElement.showModal();
    }

    close() {
        this.dlg().nativeElement.close();
    }

    // clears everything for the next upload is fresh!
    reset() {
        this.file = null;
        this.title = this.section = this.url = '';
        this.fileInput().nativeElement.value = '';
        this.loading.set(false);
        this.error.set(null);
        this.result.set(null);
    }

    // file chosen, so remember it anf guess a title (IF EMPTY)
    pick(event: Event) {
        this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
        this.result.set(null);
        this.error.set(null);
        if (this.file && !this.title) {
        this.title = this.file.name.replace(/\.txt$/i, '').replace(/[_-]/g, ' ');
        }
    }

    upload() {
        if (!this.file || this.loading()) return;
        this.loading.set(true);
        this.error.set(null);
        this.result.set(null);

        this.api.ingest(this.file, { title: this.title, section: this.section, url: this.url }).subscribe({
        next: (r) => {
            this.result.set(r);
            this.loading.set(false);
        },
        error: (e) => {
            // fast api gives reason in error detail
            const why = typeof e.error?.detail === 'string' ? e.error.detail : 'is this api running on :8000?';
            this.error.set(`upload failed (${e.error.status || 'network'}): ${why}`);
            this.loading.set(false);
        },
    });
}
}