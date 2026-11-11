// one search hit = one chunk of a doc page that matched the query
export interface SearchResult {
    text: string;       // actual text content
    score?: number;      // how well matched it is (optional since api doesnt send it yet)
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
    title: string;
    chunks_added: number;
    took_ms?: number;
    total_chunks?: number;
}

// what GET /search actually sends (timing is in seconds now yay)
export interface ApiSearchResponse {
    query: string;
    results: SearchResult[];
    execution_time?: number;    // the seconds in dennis's part
    took_ms?: number;   // a just in case
}

// what POST /ingest actually sends (from the goat himself, patrick's ingest text())
export interface ApiIngestResponse {
    source_file: string;
    title: string;
    chunks: number;
    seconds: number;
    collection_total: number;
}