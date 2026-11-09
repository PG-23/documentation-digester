import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';

export const appConfig: ApplicationConfig = {
  providers: [
    // keep the provider that CLI generated
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
  ]
};

