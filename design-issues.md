[#design] Design review issues found (from screenshot + /design-login + docs):
Login (/design-login): language buttons no-op (fixed aria-label but handlers empty), fake auth btoa() vulnerability, localStorage (needs HttpOnly cookie), design note "Design preview" present.
Main map (screenshot): Board.svelte flip animation needs stronger reduced-motion guard; no /design spec dir; auth-scheme.md unimplemented; 5 open routing review items remain.
