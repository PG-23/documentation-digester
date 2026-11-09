// one search hit = one chunk of a doc page that matched the query
export interface SearchResult {
    text: string;       // actual text content
    score: number;      // how well matched it is
    title: string;
    section?: string;   //doc section, ? = optional
    url: string;
    source_file: string;
    chunk_index: number;
}

// full response from the /search endpoint
export interface SearchResponse {
    query: string;      // question user searched for
    results: SearchResult[];
    took_ms?: number;      // this is optional but how long the search took
}

// extra info user types when uploading a page
export interface IngestMeta {
    title: string;
    section: string;
    url: string;
}

// response from /ingest endpoint after file is uploaded
export interface IngestResponse {
    source_file: string;
    chunks_added: number;
    took_ms?: number;      // this is optional but how long the ingestion took
}