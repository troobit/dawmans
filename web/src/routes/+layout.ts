// There is no server to render on: the counterpart is a Python process and every
// value on the page comes from a runtime call to it. The prerendered static shell
// paints before any network call, which is the headroom 8.7's 150 ms
// acknowledgement budget spends (Decision 1).
export const ssr = false;
export const prerender = true;
