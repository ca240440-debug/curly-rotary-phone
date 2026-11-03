# Architecture and security boundaries

## Current implementation

The application is free for families. Its potential revenue is optional, clearly disclosed affiliate shopping by adults. No payment storage, checkout, purchase automation, paid placement, advertising SDK, analytics, or third-party asset is included.

```text
Child profile session -> child projection -> own wishes + permitted catalog fields
Parent session        -> parent API        -> profiles, consent, private gift planning
                                          -> shared catalog / public price observations
                                          -> retailer adapter -> regular link
                                                              -> approved affiliate provider (future)
Approved price source (future) -> worker -> public offers -> recalculated child totals
Parent alert subscription (future)      -> adult-only delivery
```

Python's HTTP server and SQLite implement a local, single-family workflow. Profiles have nicknames, optional budgets in integer USD cents, three independent display permissions, and a high-entropy hashed access code. Optional age (not date of birth) drives suggested defaults and ordering. Parents select or override the settings; changing age does not overwrite existing choices. Advanced controls include categories, ESRB ratings, unverified games, and wish approval.

## Storage separation

- `profiles`: display permissions, budget, nickname, hashed access code.
- `products`, `offers`, `offer_prices`: shared family catalog, normalized retailer links, manually recorded public offer prices and history. Product edits are explicitly labeled shared. Custom wish ideas become family catalog entries and are visible to siblings without profile attribution.
- `wishes`: profile ownership, product, priority, and legacy data. Private purchased/reserved states, actual-paid cents, saved comparison baseline, and target price are retained here but excluded from child serialization.
- `settings`: parent password hash, permission notice version, and permission timestamp. Existing old-style lists are migrated by nickname, with codes disabled until an adult issues them. Legacy stored prices remain archived; valid old product links become offers. Old consent is not assumed to cover new visibility permissions.

Money is validated with Decimal and stored in cents for new fields. Negative, nonfinite, over-limit, and sub-cent inputs are rejected; zero is valid. Budgets are soft planning limits. List value is the cheapest known offer for one of each wish, with unknowns reported separately. Remaining budget subtracts that same value, never actual paid. Purchased/reserved items stay in every child calculation.

Parent purchase edits never mutate catalog offers. First recording actual paid snapshots the current list value as a private baseline, unless the parent supplies another baseline. Savings are baseline minus actual paid and may be negative. Subsequent public price changes update child values without touching paid amounts or baselines. Offers can be refreshed through the parent API now and through a permitted source later; the wish projection has no purchased-state branch.

## API authorization

Parent routes (parent session required):

- GET `/api/profiles`, `/api/privacy`, `/api/parent`, `/api/parent/catalog`.
- POST `/api/profiles`, `/api/profile-code`, `/api/products`, `/api/product-settings`, `/api/offers`, `/api/import-link`, `/api/update`, `/api/consent`, `/api/delete-family`.

Child routes (child profile session and current parent permission required):

- GET `/api/wishes`: only that session's profile/list, filtered public product fields, and permitted totals.
- GET `/api/catalog`: shared products filtered by parental category/rating choices and mandatory exclusions, with the same field-level visibility rules. GET `/api/requests` exposes only the child’s own approval requests, never purchase data.
- POST `/api/wishes`: only `product_id` or free-text `name`, plus `priority`; owner is derived from the session, never the request body.
- POST `/api/priority`: update only a wish belonging to that child. Sibling IDs return not found.

Child projections explicitly allow fields; they do not return raw wish rows. They omit purchase/reservation states, paid values, savings/baselines, target prices, parent shopping/price history, access hashes, other profiles, and parent links. `prices` permits offer amounts, freshness/source, wish value, and list total. `budget` independently permits the budget limit; remaining amount is returned only when both prices and budgets are enabled. `links` permits ordinary product URLs. The same checks apply to catalog and list responses on every request. No child write can change permissions, public prices, or private statuses.

Anonymous routes expose only configuration status, static assets, and authentication. No public profile directory or open wish-list endpoint exists. The first parent initializes this local instance; it is not adult-identity verification. Child codes contain 144 bits of randomness and are stored as SHA-256 hashes. Codes can be rotated, invalidating existing child sessions. Session tokens are random and role-scoped, held in browser memory and server memory, with one-hour parent/eight-hour child expiry. Restart invalidates all sessions. Login attempts are limited per local IP.

Parent logout clears private DOM before network operations. Request/render sequence checks prevent an older asynchronous response from replacing a newer screen or role. Child screens refresh every 30 seconds when visible and after interactions. A permission change takes effect on the next API request; already delivered data cannot be recalled from a browser, screenshot, or external store.

POST endpoints require JSON, bound request size, and same-origin checks. Static and API responses use no-store, no-referrer, nosniff, and a restrictive Content Security Policy including frame denial. All UI text is rendered with textContent; illustrations are local assets. Explicit native app origins can be allowlisted using WISHNEST_APP_ORIGINS; no wildcard CORS is enabled. SQLite transaction rollback prevents partial private updates on validation failure. The server binds only to loopback and suppresses request logs.

## Retailer and affiliate boundary

`retailers.py` normalizes Amazon.com, Walmart.com, and Target.com product URLs, rejecting arbitrary destinations, credentials, nonstandard ports, redirects, shortened links, and non-product paths. Tracking query strings and fragments are removed. There is no server fetch of arbitrary user URLs.

Each retailer's optional `AffiliateProvider` receives only a normalized product URL, never child/profile/family identifiers. Current providers are unset. Parent responses include link disclosure, affiliate status, and a clean edit URL. Child responses bypass affiliate providers entirely. Links omit referrers and open with noopener/noreferrer; parent affiliate links additionally use sponsored. Child links ask for a browsing confirmation and clearly leave the app. No commission-based ranking of wishes is allowed.

Before configuring an affiliate account, confirm approval and current program rules, permitted child-directed-service use, destination validation, placement, attribution, required disclosures, and data-processing restrictions. If approved Amazon participation is added, include its required statement, “As an Amazon Associate I earn from qualifying purchases,” as required by current terms. Check Walmart/network terms independently. Disclosures must stay adjacent to adult shopping links. Do not assume direct cart APIs exist.

## Future price integration and alerts

`pricing.py` specifies a price observation with amount, currency, source, product URL, and observation time. No collector, API key, scheduler, or automatic alert delivery is enabled. Integrate only approved feeds, preserving their caching, display, history, retention, and rate-limit rules. Reject stale/invalid observations and enforce currency. Extend the offer update boundary with trusted provider identity and idempotent observation handling before enabling a worker; do not reuse a child's session for collection.

Scheduled price refresh must operate on products independently of private wish status. Target matching, notification subscriptions, and delivery stay in adult-only services. Add verified parent delivery destinations, explicit opt-in, unsubscribe/revocation, quiet hours, duplicate suppression, retries, freshness checks, and audit retention. No notifications to children. A target match must not claim to predict the best future price.

## Privacy and public launch

The permission notice records an explicit adult action, notice version, and UTC time before child profiles can be created/accessed. Parents choose external-browsing permissions, allowing a range of maturity levels with optional age suggestions and without birth-date collection. The local permission record is not verified parental consent or a compliance certification.

Nicknames and free-text wishes can still contain identifying details; the UI requests minimization and adult supervision. Only explicitly allowed browsing transfers requests to retailers, whose policies and checkout cannot be controlled by this app. Child sessions have no payment or purchasing functions within the application. Use supervision or browser/device restrictions if a child must not reach external checkout.

Authenticated family deletion removes profiles, wishes, products, observations, purchases, and permission and invalidates child sessions. Parent password is retained to prevent takeover. Secure SQLite deletion is enabled, but external snapshots/backups require a separate retention and deletion policy.

Before public deployment add real adult accounts and secure recovery, family/tenant scoping for every query and worker, verified parental consent where required, HTTPS hosting, appropriate HttpOnly/SameSite session handling, centralized rate/session stores, production security review, child privacy/legal review, operator-specific policies/contact details, parental review/export rights, retention enforcement, backup erasure, accessibility validation, and approved retailer integrations. Never deploy this loopback single-family server as a public multi-tenant service.

Tests exercise child response noninterference: private purchase changes leave the entire child list and catalog responses identical. Additional tests cover authorization, code rotation, budgets, permissions, atomic edits, migration, and deletion. A real Chromium smoke test exercises desktop parent and mobile child workflows. These checks are evidence of implemented behavior, not a legal/security certification.


## Unified discovery and age/content controls

`catalog.py` defines provider-neutral products/offers and disabled connection status for Amazon, Walmart, and Target. It seeds 11 fictional examples once with original local SVG illustrations, categories, fictional comparisons, and sample game ratings; it never creates checkout links for sample data. A persistent seed marker prevents re-creation after family deletion. Manual links/data are clearly distinguished. The provider contract reserves source IDs, licensed-image references, verified rating provenance, observation time/currency, age suggestions, and mandatory exclusions. Actual ingestion, authorization, identity matching/deduplication, retention, and image licensing need approved provider implementations. None is enabled.

Search/category filtering runs in the local client after the authenticated server enforces permissions. Every product card has one large add button. Primary discovery never requires URLs, retailer navigation, or an OS share sheet. Optional parent-only `/api/import-link` normalizes supported product URLs and inserts manual records without fetching anything. Web Share Target input is untrusted, staged in memory, removed from history, and gated by adult sign-in and review. Native share extensions are not implemented.

`recommendations.py` separates three layers:

1. Optional age recommendations rank/label products; they do not establish eligibility. Default suggestions can be applied by an adult. Existing preferences survive age changes unless explicitly replaced.
2. Parent content preferences control category lists, ESRB E/E10+/T/M/unrated games, and whether unverified games are allowed. A 12-year-old can access an M-rated game if explicitly permitted, including the unverified choice when applicable. Ratings are marked verified only by trusted-source metadata. Manual metadata edits cannot assert verification; editing clears it. No live verification source exists in this MVP.
3. Nonempty trusted `mandatory_restriction` metadata excludes products regardless of preferences, even if an unknown restriction code is encountered. No parent/child API can remove or set those trusted flags. This is a policy boundary, not an exhaustive legal-compliance engine: a production ingestion service must determine and enforce applicable region/retailer/platform restrictions and reject ineligible content. Free-text manual imports cannot automatically classify all safety/legal issues. No claim of universal regulatory compliance is made.

If parental settings exclude an existing approved wish, the child receives a generic placeholder with no product details, offers, or monetary value. It is not deleted, and the parent retains the original. This applies independently of purchase/reservation state. Mandatory exclusions likewise cannot be bypassed via guessed product IDs or approval actions.

Optional wish approval inserts `pending` requests; only `approved` rows enter child wishes and totals. Requests are visible in a separate child request section and adult review queue. Declined requests remain outside the list. Child request responses include only own request ID, safe title, product ID, and review outcome. Parent-only approval cannot be performed by a child. Purchase edits do not change review outcomes. Existing migrated wishes remain approved, preserving prior work.

## Native packaging and remaining delivery work

Generated Capacitor iOS/Android projects reuse the UI and API. `scripts/prepare-mobile.cjs` builds either an intentionally unconnected scaffold or an explicitly configured HTTPS-API build. Native scaffolds have been generated/synced, not compiled/signed/device-tested. Web APIs and native origins are documented in `mobile.md`. No production backend or multi-family hosting has been deployed. The manifest and noncaching service worker support optional compatible web installation/share flows, not an offline authenticated app.
