### SvelteKit

- **Svelte 5 uses runes.** `$state`, `$derived`, `$effect`, `$props` — not
  `writable`/`readable` stores and not `export let`. Both spellings still work,
  which is why this is worth saying: a legacy-style component will run, and will
  be the odd one out forever.
- **Only prefixed environment variables reach the browser.** SvelteKit exposes
  `PUBLIC_*` and Vite exposes `VITE_*`. Adding one means adding it to the
  frontend's example env file in the same change.
