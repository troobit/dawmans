// The fake SSE server for the browser suite (design "Testing Strategy"): the
// engine's HTTP surface as scripted fixtures, so no Playwright test needs a
// provider, a corpus or a key. Scripts are selected by the question text; the
// vite dev proxy in front of this rewrites Origin, exactly as in real dev.

import { createServer } from 'node:http';

const PORT = Number(process.env.STUB_ENGINE_PORT ?? 8788);
const TURN_STREAM_HEADER = 'dawmans-turn-stream';
const TURN_STREAM_VERSION = 'dawmans/turn-stream/1';

// ---------------------------------------------------------------------------
// Fixtures

const SOURCES = {
	sources: [
		{
			kind: 'vendor-manual',
			source_id: 'ableton/live-12',
			display_name: 'Ableton Live 12 Manual',
			vendor: 'ableton',
			product: 'live-12',
			doctype: 'manual',
			lang: 'en',
			doc_version: '12',
			page_count: 700,
			low_text: false,
			hardware_applicability: { status: 'confirmed' },
			ingested_at: '2026-08-01T00:00:00Z',
			chunk_count: 40
		},
		{
			kind: 'vendor-manual',
			source_id: 'akai/apc-key-25',
			display_name: 'Akai APC Key 25 Manual',
			vendor: 'akai',
			product: 'apc-key-25',
			doctype: 'manual',
			lang: 'en',
			doc_version: '1.0',
			page_count: 24,
			low_text: false,
			hardware_applicability: { status: 'assumed', device: 'apc-key-25-mk1' },
			ingested_at: '2026-08-01T00:00:00Z',
			chunk_count: 8
		},
		{
			kind: 'authored-triage',
			source_id: 'authored/triage',
			display_name: 'Your triage notes',
			hardware_applicability: { status: 'assumed' },
			ingested_at: '2026-08-01T00:00:00Z',
			chunk_count: 4
		}
	],
	owned_but_undocumented: [],
	documented_but_unconfirmed: []
};

const VENDOR_CITE = {
	kind: 'vendor-manual',
	source_id: 'ableton/live-12',
	display_name: 'Ableton Live 12 Manual',
	passage_id: 'passage-vendor-0001',
	section_number: '14.2',
	section_title: 'Routing',
	hardware_applicability: { status: 'confirmed' },
	degraded: false,
	has_figures: false,
	doc_version: '12',
	page: 312
};

const AUTHORED_CITE = {
	kind: 'authored-triage',
	source_id: 'authored/triage',
	display_name: 'Your triage notes',
	passage_id: 'passage-authored-0001',
	section_title: 'No sound from the master',
	hardware_applicability: { status: 'assumed' },
	degraded: false,
	has_figures: false,
	entry_location: 'triage/no-sound.md:12'
};

const PASSAGES = {
	'passage-vendor-0001': {
		passage_id: 'passage-vendor-0001',
		source_id: 'ableton/live-12',
		section_number: '14.2',
		section_title: 'Routing',
		page_start: 312,
		page_end: 312,
		text: 'Set the monitor switch to Auto and check the master mute.',
		degraded: false,
		has_figures: false
	},
	'passage-authored-0001': {
		passage_id: 'passage-authored-0001',
		source_id: 'authored/triage',
		section_title: 'No sound from the master',
		text: 'Check the Cue/Master switch on the mixer first.',
		degraded: false,
		has_figures: false,
		entry_location: 'triage/no-sound.md:12'
	}
};

// A minimal one-page PDF — enough for the serve-document route to answer with
// a real document rather than an error page.
const TINY_PDF = Buffer.from(
	`%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f
trailer<</Size 4/Root 1 0 R>>
startxref
0
%%EOF
`
);

// ---------------------------------------------------------------------------
// Turn scripts, selected by the question text

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Streamed long answer: citations early, ~2.5 s of deltas — for no-reflow and mid-stream tests. */
async function streamedAnswer(emit) {
	emit('outcome', { outcome: 'answered' });
	emit('direct_answer', { text: 'Unmute the master track.' });
	emit('citation', VENDOR_CITE);
	emit('citation', AUTHORED_CITE);
	emit('body_delta', { text: '## Routing\n' });
	// Long enough that the thread container overflows and keeps growing — the
	// no-reflow and reading-position tests both need real movement to push
	// against.
	for (let step = 1; step <= 24; step += 1) {
		emit('body_delta', { text: `${step}. Check item ${step} in the routing panel ` });
		await sleep(60);
		emit('body_delta', { text: `and confirm the meter moves [[p:passage-vendor-0001]].\n` });
		await sleep(60);
	}
	// A quiet stretch before the final line: the reading-position test collapses
	// its expanded citation here, mid-stream but without a racing paint.
	await sleep(2500);
	emit('body_delta', { text: 'The mixer notes say the Cue switch hides mutes ' });
	await sleep(60);
	emit('body_delta', { text: '[[p:passage-authored-0001]].\n' });
	emit('done', { complete: true });
}

async function quickAnswer(emit) {
	emit('outcome', { outcome: 'answered' });
	emit('direct_answer', { text: 'Unmute the master track.' });
	emit('citation', VENDOR_CITE);
	emit('citation', AUTHORED_CITE);
	emit('body_delta', {
		text: 'Check the mutes [[p:passage-vendor-0001]].\nThen the Cue switch [[p:passage-authored-0001]].\n'
	});
	emit('contributing_sources', { sources: ['ableton/live-12', 'authored/triage'] });
	emit('done', { complete: true });
}

async function narrowing(emit) {
	emit('outcome', { outcome: 'needs-narrowing' });
	emit('narrowing', {
		question: 'No sound from where?',
		candidates: [
			{ label: 'Live shows no output', value: 'From Live on the laptop' },
			{ label: 'The APC pads are unlit', value: 'From the APC pads' }
		]
	});
	emit('done', { complete: true });
}

/** Long silence before any content — the waiting-indicator and cancel window. */
async function slowAnswer(emit, aborted) {
	for (let waited = 0; waited < 8000; waited += 200) {
		if (aborted()) return;
		await sleep(200);
	}
	emit('outcome', { outcome: 'answered' });
	emit('direct_answer', { text: 'Finally: unmute the master track.' });
	emit('done', { complete: true });
}

/**
 * An unknown outcome and a stream that ends without `done`: the turn fails
 * as broken (9.4, 9.14), which is what gives the state line its ✕ channel.
 */
async function brokenOutcome(emit) {
	emit('outcome', { outcome: 'mystery', detail: 'stub detail text' });
}

function scriptFor(question) {
	const text = question.toLowerCase();
	if (text.includes('narrow')) return narrowing;
	if (text.includes('slow')) return slowAnswer;
	if (text.includes('steps')) return streamedAnswer;
	if (text.includes('break')) return brokenOutcome;
	return quickAnswer;
}

// ---------------------------------------------------------------------------
// The server

function json(response, body) {
	response.writeHead(200, { 'content-type': 'application/json' });
	response.end(JSON.stringify(body));
}

function readBody(request) {
	return new Promise((resolve) => {
		let raw = '';
		request.on('data', (chunk) => {
			raw += chunk;
		});
		request.on('end', () => resolve(raw));
	});
}

const server = createServer(async (request, response) => {
	const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
	const path = url.pathname;

	if (request.method === 'POST' && path === '/turn') {
		const body = JSON.parse(await readBody(request));
		let aborted = false;
		request.on('close', () => {
			aborted = true;
		});
		response.writeHead(200, {
			'content-type': 'text/event-stream',
			'cache-control': 'no-cache',
			[TURN_STREAM_HEADER]: TURN_STREAM_VERSION
		});
		const emit = (event, data) => {
			if (!aborted) response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
		};
		await scriptFor(body.question)(emit, () => aborted);
		response.end();
		return;
	}
	if (request.method === 'GET' && path === '/sources') return json(response, SOURCES);
	if (request.method === 'GET' && path === '/provider') {
		return json(response, { kind: 'local', model: 'ollama/llama3', masked: null });
	}
	if (path.startsWith('/provider')) {
		// PUT /provider, credential routes and the test operation: enough of an
		// answer that the configuration surface works; state is not retained.
		if (request.method === 'POST' && path === '/provider/test') {
			return json(response, { reachable: true });
		}
		await readBody(request);
		return json(response, { kind: 'local', model: 'ollama/llama3', masked: null });
	}
	if (request.method === 'GET' && path.startsWith('/passages/')) {
		const passage = PASSAGES[path.slice('/passages/'.length)];
		if (passage === undefined) {
			response.writeHead(404, { 'content-type': 'application/json' });
			return response.end('{}');
		}
		return json(response, passage);
	}
	if (request.method === 'GET' && /^\/sources\/.+\/document$/.test(path)) {
		response.writeHead(200, { 'content-type': 'application/pdf' });
		return response.end(TINY_PDF);
	}
	response.writeHead(404, { 'content-type': 'application/json' });
	response.end('{}');
});

server.listen(PORT, '127.0.0.1', () => {
	console.log(`stub engine listening on http://127.0.0.1:${PORT}`);
});
