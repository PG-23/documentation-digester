import { Component, signal } from '@angular/core';
import { SearchComponent } from './search/search.component';

@Component({
  selector: 'app-root',
  imports: [SearchComponent],
  template: `
    <h1>Documentation Digester</h1>
    <!--  search box w/ results--> 
    <app-search />
  `,
})
export class App {}
