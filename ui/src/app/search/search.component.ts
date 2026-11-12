// chat area: the sun/moon thingy in the background

import { UploadDialogComponent } from "../upload/upload-dialog.component";
import { Component, inject, signal, ElementRef, computed, effect, viewChild } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { DecimalPipe, PercentPipe } from "@angular/common";
import { SearchStore } from "../search-store.service";
import { SearchResult } from "../models";

@Component({
    selector: 'app-search',

    host: { class: 'chat' },

    imports: [UploadDialogComponent, FormsModule, DecimalPipe, PercentPipe],
    template: `
        <!-- file cabinet art: closed cabinet w/3 drawers that slide out one at a time -->
        <div class="art cabinet" aria-hidden="true">

          <!-- sunshine cabinet -->
          <div class="cab-set set-sun">
            <div class="layer cab-body"></div>
            <div class="drawer-clip"><div class="layer drawer d1"></div></div>
            <div class="drawer-clip"><div class="layer drawer d2"></div></div>
            <div class="drawer-clip"><div class="layer drawer d3"></div></div>
          </div>

          <!-- midnight cabinet -->
          <div class="cab-set set-moon">
            <div class="layer cab-body"></div>
            <div class="drawer-clip"><div class="layer drawer d1"></div></div>
            <div class="drawer-clip"><div class="layer drawer d2"></div></div>
            <div class="drawer-clip"><div class="layer drawer d3"></div></div>
          </div>
        </div>

        <div class="thread" #thread aria-live="polite">

        <!-- welcome bubble when the chat is empty -->
        @if (!store.messages().length) {
            <div class="bubble bot welcome">
            <b>Hi!</b>ask anything about the Godot docs, or pick a question on the left
            </div>
        }

        <!-- each message = your question n the results -->
        @for (m of store.messages(); track m.id) {
            <div class="bubble user">{{ m.query }}</div>

            <div class="bubble bot">
            <!-- show different things depending on the status -->
            @switch (m.status) {
                @case ('loading') {
                <p class="meta">searching the docs…</p>
                }
                @case ('error') {
                <p class="error">{{ m.error }}</p>
                }
                @case ('finish') {
                @if (m.response; as r) {
                    <p class="meta">
                    {{ r.results.length }} results
                    @if (r.took_ms != null) { · {{ r.took_ms | number: '1.0-0' }} ms }
                    </p>

                    <div class="results">
                    @for (res of r.results; track key(res); let i = $index) {
                        <article class="card">
                        <header class="card-head">
                            <span class="rank">#{{ i + 1 }}</span>
                            <h3 class="card-title">
                            <a [href]="res.url" target="_blank" rel="noopener">{{ res.title || 'untitled' }}</a>
                            </h3>
                            @if (res.score != null) {
                            <span class="score" [title]="'Relevance score: ' + (res.score | number: '1.3-3')">
                                {{ clamp(res.score) | percent: '1.0-0' }} match
                            </span>
                            }
                        </header>

                        @if (res.score != null) {
                            <div class="score-bar" aria-hidden="true">
                            <i [style.width.%]="clamp(res.score) * 100"></i>
                            </div>
                        }

                        <p class="text" [class.expanded]="isExpanded(m.id, res)">{{ res.text }}</p>
                        @if (res.text.length > 280) {
                            <button type="button" class="link-btn" (click)="toggle(m.id, res)">
                            {{ isExpanded(m.id, res) ? 'Show less' : 'Show more' }}
                            </button>
                        }

                        <!-- Metadata chips + source link -->
                        <footer class="card-foot">
                            @if (res.section) { <span class="chip">{{ res.section }}</span> }
                            <span class="chip mono">{{ res.source_file }}</span>
                            <span class="chip mono">chunk {{ res.chunk_index }}</span>
                            @if (res.url) {
                            <a class="source-link" [href]="res.url" target="_blank" rel="noopener">Open in Godot docs ↗</a>
                            }
                        </footer>
                        </article>
                    } @empty {
                        <p class="meta">no results, try rephrasing your question</p>
                    }
                    </div>
                }
                }
            }
            </div>
        }
        </div>

        <!-- input bar pinned at the bottom -->
        <div class="composer">
        <form (ngSubmit)="send()">
            <input
            name="q"
            [(ngModel)]="query"
            placeholder="ask about the Godot docs…"
            autocomplete="off"
            aria-label="search question"
            />

            <select name="k" [ngModel]="store.k()" (ngModelChange)="store.k.set($event)" aria-label="number of results">
            @for (n of [3, 5, 10]; track n) {
                <option [ngValue]="n">Top {{ n }}</option>
            }
            </select>

             <!-- opens the upload pop-up, upload = a handle to the dialog component -->
            <button type="button" class="upload-btn" (click)="upload.open()">📎 upload a page</button>
        </form>
        <app-upload-dialog #upload />
        </div>
    `,
})
export class SearchComponent {
    protected store = inject(SearchStore);

    query = '';     //text in input bar

    private expanded = signal<Set<string>>(new Set());
    private thread = viewChild<ElementRef<HTMLElement>>('thread');  // scrollable thread element
    private count = computed(() => this.store.messages().length);  // # of messages, computed only 'changes'

    constructor() {
        effect(() => {
            this.count();
            const el = this.thread()?.nativeElement;
            if (el) setTimeout(() => el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }));
        });
    }

    // input bar submit: ask then clear box if search started
    send() {
        if(this.store.ask(this.query)) this.query = '';
    }

    key(res: SearchResult): string {
        return `${res.source_file}#${res.chunk_index}`;
    }

    isExpanded(msgId: number, res: SearchResult): boolean {
        return this.expanded().has(`${msgId}:${this.key(res)}`);
    }

    toggle(msgId: number, res: SearchResult) {
        const k = `${msgId}:${this.key(res)}`;
        const next = new Set(this.expanded());
        next.has(k) ? next.delete(k) : next.add(k);
        this.expanded.set(next);
    }

    // keep score between 0-1 for the % n the bar
    clamp(score: number): number {
        return Math.max(0, Math.min(1, score));
    }
}
