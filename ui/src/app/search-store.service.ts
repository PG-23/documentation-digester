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

// saved chat (under "recents")
export interface Conversation {
    id: string;
    title: string;
    updatedAt: number;
    messages: Message[];
}

const CHATS_KEY = 'dd-recent';
const MAX_CHATS = 20;

@Injectable({ providedIn: 'root' })
export class SearchStore {
    private api = inject(ApiService);
    private nextId = 1;

    readonly chats = signal<Conversation[]>([]);  // saved chats, newest first
    readonly activeId = signal<string| null>(null);  // chat currently open
    readonly messages = signal<Message[]>([]);      // messages of open chat
    readonly k = signal(5);  // how many results to ask for
    readonly busy = computed (() => this.messages().some((m) => m.status === 'loading'));  // true while any search is still loading

    constructor() {
        localStorage.removeItem('dd-recent');  // clears up old convos list
    }

    ask(query: string): boolean {
        const q = query.trim();
        if(!q || this.busy()) return false;

        // first question in a new chat -> creates the chat
        if(!this.activeId()) {
            this.activeId.set(Date.now().toString(36) + Math.random().toString(36).slice(2, 6));
        }

        const id = this.nextId++;
        this.messages.update((list) => [...list, { id, query: q, status: 'loading'}]);
        this.save();

        // calls the api then updates that same message w/result
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
        if(this.busy()) return;
        this.activeId.set(null);
        this.messages.set([]);
    }

    // reopen a saved chat from recent list
    openChat(chatId: string) {
        if(this.busy()) return;
        const chat = this.chats().find((c) => c.id === chatId);
        if(!chat) return;
        this.activeId.set(chat.id);
        this.messages.set(chat.messages);

        // keeps message id unique when new questions get added
        this.nextId = Math.max(0, ...chat.messages.map((m) => m.id)) + 1;
    }

    // delete chat (if opened, start fresh)
    deleteChat(chatId: string) {
        this.chats.update((list) => list.filter((c) => c.id !== chatId));
        this.persist();
        if(this.activeId() === chatId) this.newSearch;
    }

    // delete all chats
    clearChats() {
        this.chats.set([]);
        localStorage.removeItem(CHATS_KEY);
        this.newSearch();
    }

    private patch(id: number, changes: Partial<Message>) {
        this.messages.update((list) => list.map((m) => (m.id) === id ? {...m, ...changes } : m));
        this.save();
    }

    // copy the open chat into chat lists (write to localstorage)
    private save() {
        const chatId = this.activeId();
        const messages = this.messages().filter((m) => m.status !== 'loading');   // don't save half-finished searches
        if (!chatId || !messages.length) return;

        const first = messages[0].query;
        const chat: Conversation = {
            id: chatId,
            title: first.length > 40 ? first.slice(0, 40) + '…' : first,
            updatedAt: Date.now(),
            messages,
        };

        this.chats.update((list) =>
            [chat, ...list.filter((c) => c.id !== chatId)]   // move it to the top
                .slice(0, MAX_CHATS),
        );
        this.persist();
    }

    private persist() {
        try {
            localStorage.setItem(CHATS_KEY, JSON.stringify(this.chats()));
        } catch {
            // storage full: drop the oldest half and try once more
            this.chats.update((list) => list.slice(0, Math.ceil(list.length / 2)));
            try { localStorage.setItem(CHATS_KEY, JSON.stringify(this.chats())); } catch {}
        }
    }

    // read saved chats (empty list if missing/broken)
    private loadChats(): Conversation[] {
        try {
            const saved = JSON.parse(localStorage.getItem(CHATS_KEY) ?? '[]');
            return Array.isArray(saved) ? saved.slice(0, MAX_CHATS) : [];
        } catch {
            return [];
        }
    }
}