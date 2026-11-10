// this is for theme only so the sunshine/midnight theme

import { Injectable, effect, signal } from "@angular/core";

export type Theme = 'sunshine' | 'midnight';

// used to save the choice in browser
const STORAGE_KEY = 'dd-theme'; 

@Injectable({ providedIn: 'root' })
export class ThemeService {
    readonly theme = signal<Theme>(this.initialTheme());

    constructor() {
        effect(() => {
            const t = this.theme();
            document.documentElement.dataset['theme'] = t;
            localStorage.setItem(STORAGE_KEY, t);
        });
    }

    // flip between 2 themes
    toggle() {
        this.theme.update((t) => (t === 'sunshine' ? 'midnight' : 'sunshine'));
    }

    // pick the starting theme
    private initialTheme(): Theme {
        const saved = localStorage.getItem(STORAGE_KEY);
        if(saved === 'sunshine' || saved === 'midnight') return saved;

        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'midnight' : 'sunshine';
    }
}