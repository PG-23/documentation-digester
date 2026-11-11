// the left sidebar

import { Component, inject } from '@angular/core';
import { SearchStore } from '../search-store.service';

// questions that should return good results from doc subset
// prolly will ask either gian/sohan which questions score best n put them in demo
const SUGGESTIONS = [
  'How do signals work?',
  'What is the difference between a node and a scene?',
  'How do I attach a script to a node?',
  'Which scripting languages does Godot support?',
];

@Component({
    selector: 'app-sidebar',
    host: { class: 'sidebar'},

    template: `
    <div class="brand">Documentation<br />Digester</div>
    <nav class="side-panel" aria-label="Searches">

    <!-- clears the chat -->
    <button type="button" class="new-btn" (click)="store.newSearch()">＋ new search</button>

     <!-- clicks suggestion = run that search -->
      <section class="side-section">
        <h3>Try asking</h3>
        @for (q of suggestions; track q) {
          <button type="button" class="side-link" (click)="store.ask(q)" [disabled]="store.busy()">
            {{ q }}
          </button>
        }
      </section>

      @if (store.recent().length) {
        <section class="side-section">
          <div class="side-head">
            <h3>Recent</h3>
            <button type="button" class="clear-btn" (click)="store.clearRecent()">clear</button>
          </div>
          @for (q of store.recent(); track q) {
            <button type="button" class="side-link" (click)="store.ask(q)" [disabled]="store.busy()">
              {{ q }}
            </button>
          }
        </section>
      }

    </nav>
    `
})
export class SidebarComponent {
    // 'protected' = usable in template
    protected store = inject(SearchStore);
    protected suggestions = SUGGESTIONS;
}