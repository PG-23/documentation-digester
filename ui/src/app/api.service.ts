// only file that talks to backend, components call these methods instead of using
// HttpClient directly, so if api changes, only fix it in one place

import { Injectable, inject } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { Observable, delay, of } from "rxjs";
import { IngestMeta, IngestResponse, SearchResponse } from "./models";
import { MOCK_SEARCH } from "./mock-data";

// true = use fake data, false = call real FastAPI backend
// flip to false once Dennis's /search n /ingest are running on :8000
const USE_MOCK = false;

@Injectable({ providedIn: 'root'})
export class ApiService {
    private http = inject(HttpClient);

    // search(): sends user's question to /search n gets back results
    // k = how many results to return (default to 5)
    search(query: string, k = 5): Observable<SearchResponse> {
        // mock mode: return fake data (w/users query filled in) after 300ms
        if(USE_MOCK) return of({ ...MOCK_SEARCH, query }).pipe(delay(300));

        //real mode: the api uses GET w/query params -> /search?query=...&k=...
        return this.http.get<SearchResponse>('/search', { params: { query, k }});
    }

    // ingest(): uploads a txt file n its metadata to /ingest so the backend can chunk it
    // embed it n store it in vector db
    ingest(file: File, meta: IngestMeta): Observable<IngestResponse> {
        if(USE_MOCK) {
            return of(
                { source_file: file.name, chunks_added: 7, took_ms: 850}).pipe(delay(800));
        }

    // formdata = format browsers use to upload files
    const form = new FormData();
    form.append('file', file);
    form.append('title', meta.title);
    form.append('section', meta.section);
    form.append('url', meta.url);

    return this.http.post<IngestResponse>('/ingest', form);
    }

    // health(): asks the API "are u alive?" then show a status badge
    health(): Observable<{ status: string }> {
        // mock mode: report "mock" so its obvi its not on real api
        if(USE_MOCK) return of({ status: 'mock' });

        // real mode: GET /health, expected to return sum like { status: ok }
        return this.http.get<{ status: string }>('/health');
    }
}