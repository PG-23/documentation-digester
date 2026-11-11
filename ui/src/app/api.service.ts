// only file that talks to backend, components call these methods instead of using
// HttpClient directly, so if api changes, only fix it in one place

import { Injectable, inject } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { Observable, delay, of, map } from "rxjs";
import { MOCK_SEARCH } from "./mock-data";
import { ApiIngestResponse, ApiSearchResponse, IngestMeta, IngestResponse, SearchResponse } from "./models";

// true = use fake data, false = call real FastAPI backend
// flip to false once Dennis's /search n /ingest are running on :8000
const USE_MOCK = false;

@Injectable({ providedIn: 'root'})
export class ApiService {
    private http = inject(HttpClient);

    // search(): sends user's question to /search n gets back results
    // k = how many results to return (default to 5)
    search(query: string, k = 5): Observable<SearchResponse> {
        if(USE_MOCK) return of({ ...MOCK_SEARCH, query }).pipe(delay(300));

        return this.http.get<ApiSearchResponse>('/search', { params: { query, k }}).pipe(
            // convert api timing into the ms
            map((r) => ({
                query: r.query,
                results: r.results,
                // in case if api uses ms, if not then seconds -> ms
                took_ms: r.took_ms ?? (r.execution_time != null ? r.execution_time * 1000 : undefined),
            })),
        );
    }

    // ingest(): uploads a txt file n its metadata to /ingest so the backend can chunk it
    // backend chunks it, embed it n store it in vector db
    ingest(file: File, meta: IngestMeta): Observable<IngestResponse> {
        if(USE_MOCK) {
            return of(
                { source_file: file.name, title: meta.title, chunks_added: 7, took_ms: 850, total_chunks: 120,}).pipe(delay(800));
        }

    // formdata = format browsers use to upload files
    const form = new FormData();
    form.append('file', file);
    form.append('title', meta.title);
    form.append('section', meta.section);
    form.append('url', meta.url);

    return this.http.post<ApiIngestResponse>('/ingest', form).pipe(
        map((r) => ({
            source_file: r.source_file,
            title: r.title,
            chunks_added: r.chunks,
            took_ms: r.seconds * 1000,
            total_chunks: r.collection_total,
        })),
    );
    }

    // health(): asks the API "are u alive?" then show a status badge
    health(): Observable<{ status: string }> {
        // mock mode: report "mock" so its obvi its not on real api
        if(USE_MOCK) return of({ status: 'mock' });

        // real mode: GET /health, expected to return sum like { status: ok }
        return this.http.get<{ status: string }>('/health');
    }
}