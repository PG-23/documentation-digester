// shared state for searching, the sidebar ('try again' or 'recent')

import { Injectable, computed, inject, signal } from "@angular/core";
import { ApiService } from "./api.service";
import { SearchResponse } from "./models";

export interface Message {
    id: number;
    query: string;
    status: 'loading' | 'finish' | 'error';
    response?: SearchResponse;
    error?: string; 
}

const RECENT_KEY = 'dd-recent';
const MAX_RECENT = 5;

@Injectable({ providedIn: 'root' })
export class SearchStore {
    private api = inject(ApiService);
    private nextId = 1;

    readonly messages = signal<Message[]>([]);  // all messages in current chat
    readonly recent = signal<string[]>(this.loadRecent());  // last few searches (survives refresh btw)
    readonly k = signal(5);  // how many results to ask for
    readonly busy = computed (() => this.messages().some((m) => m.status === 'loading'));  // true while any search is still loading

    ask(query: string): boolean {
        const q = query.trim();
        if(!q || this.busy()) return false;

        const id = this.nextId++;
        this.messages.update((list) => [...list, { id, query: q, status: 'loading'}]);

        // calls the api then uupdates that same message w/result
        this.api.search(q, this.k()).subscribe({
            next: (r) => this.patch(id, { status: 'finish', response: r }),
            error: (e) =>
                this.patch(id, {
                    status: 'error',
                    error: `search failed (${e.status || 'network'}), is this API running on :8000`,
                }),
        });
        return true;
    }

    // + new search = clear the chat (recent searches stay) & empty recent list
    newSearch() {
        this.messages.set([]);
    }

    clearRecent() {
        this.recent.set([]);
        localStorage.removeItem(RECENT_KEY);
    }

    private patch(id: number, changes: Partial<Message>) {
        this.messages.update((list) => list.map((m) => (m.id) === id ? {...m, ...changes } : m));
    }

    // put a query on the top of 'recent' (no dupes, max 5) n save it
    private remember(q: string) {
        const next = [q, ...this.recent().filter((x) => x.toLowerCase() != q.toLowerCase())].slice(0, MAX_RECENT);
        this.recent.set(next);
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    }

    // read saved recent searches
    private loadRecent(): string[] {
        try {
            const saved = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
            return Array.isArray(saved) ? saved.slice(0, MAX_RECENT): [];
        } catch {
            return [];
        }
    }
}