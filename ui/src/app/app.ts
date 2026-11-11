// page layout: sidebar on left, top bar (theme pill) n chat on right

import { Component, inject } from '@angular/core';
import { SearchComponent } from './search/search.component';
import { SidebarComponent } from './sidebar/sidebar.component';
import { ThemeService } from './theme.service';

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
            {{ themes.theme() === 'sunshine' ? '☀️ sunshine' : '🌙 midnight' }}
          </button>
        </header>

        <app-search />
      </div>
    </div>
  `,
})

export class App {
  protected themes = inject(ThemeService);
}
