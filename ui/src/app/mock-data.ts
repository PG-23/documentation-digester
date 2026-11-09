// fake search results, so it can be built and test the UI before real API
// apiservice returns this when USE_MOCK = true

import { SearchResponse } from "./models";

export const MOCK_SEARCH: SearchResponse = {
    query: '', 
    took_ms: 42,
    results: [
        // fake result 1:
        {
            text: "signals are Gdot's verison of the observer pattern. They allow a node to send out a message",
            score: 0.82,
            title: 'using signals',
            section: 'getting started',
            url: 'http://docs.godotengine.org/en/stable/getting_started/step_by_step/signals.html',
            source_file: 'signals.txt',
            chunk_index: 0,
        },

        // fake result 2:
        {
            text: 'a scene is a tree of nodes. you can save a scene to disk n instance it in other scenes',
            score: 0.67,
            title: 'nodes and scenes',
            section: 'getting started',
            url: 'http://docs.godotengine.org/en/stable/getting_started/step_by_step/nodes_scenes.html',
            source_file: 'nodes_and_scenes.txt',
            chunk_index: 2,
        },
    ],
};