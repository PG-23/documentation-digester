// page layout: sidebar on left, top bar (theme pill) n chat on right

import { Component, inject, signal } from '@angular/core';
import { SearchComponent } from './search/search.component';
import { SidebarComponent } from './sidebar/sidebar.component';
import { ThemeService, SKY_STEP_MS } from './theme.service';

@Component({
  selector: 'app-root',
  imports: [SidebarComponent, SearchComponent],
  template: `
    <div class="shell">
      <app-sidebar />

      <div class="main">
        <header class="topbar">
          <!-- pill shows the current theme, click to switch -->
          <button
            type="button"
            class="theme-pill"
            (click)="themes.toggle()"
            [attr.aria-label]="'Theme: ' + themes.theme() + '. Click to switch.'"
          >
          <span class="pill-window" aria-hidden="true">
              <!-- show-midnight class = slide down to the midnight label -->
              <span class="pill-track" [class.show-midnight]="themes.theme() === 'midnight'">
                <span class="pill-label">🌙</span>   <!-- top -->
                <span class="pill-label">☀️</span>   <!-- bottom -->
              </span>
            </span>
          </button>
        </header>

        <app-search />
      </div>
    </div>
  `,
})

export class App {
  protected themes = inject(ThemeService);

  // flips right away, starting the roll
  protected pillShowMidnight = signal(this.themes.theme() === 'midnight');

  private switching = false;

  switchTheme() {
    if(this.switching) return;
    this.switching = true;

    this.pillShowMidnight.update((v) => !v);
    this.themes.toggle();

    // the entire switch (sunshine -> sunset -> midnight)
    setTimeout(() => (this.switching = false), SKY_STEP_MS * 2);
  }
}
