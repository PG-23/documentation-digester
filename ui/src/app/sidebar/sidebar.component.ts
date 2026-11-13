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
    <nav class="side-panel" aria-label="Chats">

      <!-- start a fresh chat -->
      <button type="button" class="new-btn" (click)="store.newSearch()" [disabled]="store.busy()">＋ new search</button>

      <!-- saved chats, newest first -->
      <section class="side-section recents">
        <div class="side-head">
          <h3>Recents</h3>
          @if (store.chats().length) {
            <button type="button" class="clear-btn" (click)="store.clearChats()">clear</button>
          }
        </div>

        @for (chat of store.chats(); track chat.id) {
          <div class="chat-row" [class.active]="chat.id === store.activeId()">
            <button type="button" class="side-link chat-title" (click)="store.openChat(chat.id)"
                    [disabled]="store.busy()" [title]="chat.title">
              {{ chat.title }}
            </button>
            <button type="button" class="del-btn" (click)="store.deleteChat(chat.id)"
                    [attr.aria-label]="'Delete chat: ' + chat.title">×</button>
          </div>
        } @empty {
          <p class="side-empty">Your searches will show up here.</p>
        }
      </section>

      <!-- suggestions, pinned to the bottom -->
      <section class="side-section try">
        <h3>Try asking</h3>
        @for (q of suggestions; track q) {
          <button type="button" class="side-link" (click)="store.ask(q)" [disabled]="store.busy()">
            {{ q }}
          </button>
        }
      </section>
    </nav>
    `

})
export class SidebarComponent {
    // 'protected' = usable in template
    protected store = inject(SearchStore);
    protected suggestions = SUGGESTIONS;
}