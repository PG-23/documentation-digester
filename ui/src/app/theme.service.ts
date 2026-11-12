// this is for theme only so the sunshine/midnight theme 
// BUT ALSOOO for smoother animation like sunset/sunrise 

import { Injectable, effect, signal } from "@angular/core";

export type Theme = 'sunshine' | 'midnight';
export type SkyPhase = Theme | 'sunset' | 'sunrise';

// used to save the choice in browser
const STORAGE_KEY = 'dd-theme';

// timing of theme transitiong to another (1200ms = 1.2s)
export const SKY_STEP_MS = 1200;

@Injectable({ providedIn: 'root' })
export class ThemeService {
    readonly theme = signal<Theme>(this.initialTheme());
    readonly phase = signal<SkyPhase>(this.theme());

    private busy = false;

    constructor() {
        effect(() => {
            document.documentElement.dataset['theme'] = this.phase();
        });

        effect(() => {
            localStorage.setItem(STORAGE_KEY, this.theme());
        });
    }

    // flip between 2 themes (but now go through sunset/sunrise)
    toggle() {
        if(this.busy) return;   // ignore clicks mid switch
        this.busy = true;
        const next: Theme = this.theme() === 'sunshine' ? 'midnight' : 'sunshine';
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // 1. blend into themes
        this.phase.set(next === 'midnight' ? 'sunset' : 'sunrise');

        // 2. blend into final theme
        setTimeout(() => {
            this.theme.set(next);
            this.phase.set(next);
            this.busy = false;
        }, reduceMotion ? 0 : SKY_STEP_MS);
    }

    private initialTheme(): Theme {
        const saved = localStorage.getItem(STORAGE_KEY);
        if(saved === 'sunshine' || saved === 'midnight') return saved;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'midnight' : 'sunshine';
    }
}