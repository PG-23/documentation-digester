// the search box n the result cards 
// so task u-1 & u-2 from taskboard

import { Component, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { DecimalPipe } from "@angular/common";
import { ApiService } from "../api.service";
import { SearchResponse } from "../models";

@Component({
    selector: 'app-search',

    imports: [FormsModule, DecimalPipe],
    template: `
        <section class="panel">
        <h2>Search the Godot docs</h2>
        
        <form class="row" (ngSubmit)="run()">
        
        <!-- ngModel = query keeps the input n the query variable in sync
            while q is required when using ngModel inside a <form> -->
        <input name="q" [(ngModel)]="query" placeholder="ex: how do signals work?" autofocus />
        <select name="k" [(ngModel)]="k">
        @for(n of [3, 5, 10]; track n) {
            <option [ngValue]="n">Top {{ n }}</option>
        }
    </select>

    <!--  disable while loading/when box is empty -->
      <button type="submit" [disabled]="loading() || !query.trim()">
        {{ loading() ? 'Searching...' : 'Search' }}
    </button>
    </form>

    <!-- only show the error message if theres one --> 
     @if(error()) {
        <p class="error">{{ error() }}</p>
     }

    <!-- only show results once theres a response, r = short verision of result-->
     @if(response(); as r) {
        <p class="meta">
            {{ r.results.length }} results for "{{ r.query }}"
            @if(r.took_ms != null) { · {{ r.took_ms | number: '1.0-0' }} ms }
     </p>

     <!-- one card per result-->
      @for(res of r.results; track res.source_file + res.chunk_index; let i = $index) {
        <article class="card">
            <header>
                <span class="rank">#{{ i + 1 }}</span>
                <a [href]="res.url" target=_blank rel="noopener">{{ res.title }}</a>
                <span class="score">score {{ res.score | number: '1.2-2' }}</span>
      </header>
      <p class="text"> {{ res.text }}</p>

      <!-- metadata footer: section - file - chunk  # -->
       <footer>
        @if(res.section) { <span>{{ res.section }}</span> · }
        <span>{{ res.source_file }}</span> · <span>chunk {{ res.chunk_index }}</span>
      </footer>
      </article>
      } @empty {
        <p class="meta">No results</p>
      }
     }
    </section>
    `,
})
export class SearchComponent {
    private api = inject(ApiService);

    query = '';     // what user typed
    k = 5;         // how many results to request
    loading = signal(false);    // true while waiting for api
    error = signal<string | null>(null);    // error message to display
    response = signal<SearchResponse | null>(null);     // latest search response

    run() {
        const q = this.query.trim(); 
        if(!q) return;

        // clear old error and load
        this.loading.set(true);
        this.error.set(null);

        this.api.search(q, this.k).subscribe({
            // success: save response n stop loading
            next: (r) => {
                this.response.set(r);
                this.loading.set(false);
            },

            // failure: shows message n stops loading
            error: (e) => {
                this.error.set(`Search failed (${e.status || 'network'}) Is this API running on :8000?`);
                this.loading.set(false);
            },
        });
    }
}
