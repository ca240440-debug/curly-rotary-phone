# WishNest

A free, mobile-friendly Christmas wish-list app with unified product discovery and a separate parent dashboard. This MVP preserves the existing wish lists, profiles, budgets, and private purchase tracking.

## Try it now

```sh
python3 server.py
```

Run the command above from the extracted project folder containing `server.py` (Windows: use `python server.py`). Then type `http://localhost:8000` into a browser on the same computer. See [START-HERE.txt](START-HERE.txt) for step-by-step Windows and Mac instructions.

Open the local app on port 8000. Python 3.12+ is sufficient for web/API use. `PORT` changes the port; the server intentionally binds to loopback. Family data is in ignored `.local/wishes.db`; `WISHLIST_DATA` overrides it.

1. Open **Parent corner**, choose a private passphrase, and accept the current privacy notice.
2. Add a child profile with a nickname. Optionally enter age and click **Apply suggested defaults**. Adjust prices, budgets, links, and approval. Advanced settings cover categories, ESRB ratings, unverified games, and age ordering. No birth date is required.
3. Privately share the generated profile code. Sign out before handing the device over.
4. The child enters that code, searches/browses categories in the illustrated sample catalog, and taps **Add to My Wish List**. If approval is enabled, the item waits in Requests until a parent approves it.
5. Parents review requests, set budgets, add optional real product links, and privately track reservations, purchases, actual paid amounts, and savings. Purchased gifts stay on the child's list with no purchase indication.

The default catalog has **11 fictional sample products**, original illustrations, and clearly labeled made-up prices. Sample game ratings are unverified and are hidden unless parents permit unverified games and their rating. Samples have no real checkout URLs. No retailer connection, live inventory, verified rating feed, or scraping is active. Search stays within this local catalog. Set `WISHNEST_SAMPLE_PRODUCTS=0` before initializing a database to omit samples; existing data is preserved. Deleted family data does not automatically reappear after restart.

## Family controls

Each profile has its own display permissions, budget, optional age suggestions, allowed categories, ESRB E/E10+/T/M/unrated permissions, unverified-game choice, and wish-approval gate. Age suggests defaults and ordering; it never independently excludes a product. Parents may allow M-rated games for younger profiles, subject to mandatory eligibility restrictions. The app does not claim ratings are verified merely because a parent entered them. Current samples/manual ratings are labeled unverified; real verification needs an authoritative source.

A parent can show budget limits independently of individual prices; list totals/remaining amounts require price visibility. Values use the cheapest known offer for one of each approved wish, including purchased/reserved gifts. Unknown prices are excluded with a warning. Sample totals explicitly identify included fictional values. Budgets are planning guides, not hard spending limits or payment balances.

Parent purchase edits never change public offers or child responses. Actual paid and savings use private saved baselines, independent of later public price updates. Child APIs omit private states, amounts paid, savings, baselines, targets, and parent activity. Parent settings and review actions require adult sessions; children cannot override them. Data refreshes after actions and every 30 seconds while the child page is visible.

## Optional retailer fallback

Parents can manually import Amazon.com, Walmart.com, or Target.com product links, with an optional recorded price. A shared link also requires parent review and does not fetch metadata. Compatible installed Android web apps may support the optional Web Share Target; native share extensions are not implemented. Neither copying URLs nor sharing is required for the primary sample discovery experience.

Ordinary product links can open retailer product/checkout pages from the parent dashboard. A parent may permit child external browsing, but this app cannot control checkout on an external website. WishNest itself has no payment methods, checkout, retailer-account connections, or purchase automation. Current links earn no commission; approved affiliate providers can be added later and remain adult-only.

## iOS and Android

Capacitor source projects exist in `android/` and `ios/`. They are development scaffolds, **not signed downloadable releases**. Native use requires a hosted HTTPS backend, SDK/device testing, signing, and store publication. See [mobile build instructions](docs/mobile.md). The web experience runs now without these tools.

## Validate

```sh
python3 -m unittest discover -s tests -v
node --check public/app.js
# Optional: requires Playwright and Chromium on the host
node tests/browser.cjs
node tests/catalog-browser.cjs
# Requires Node/npm; installs pinned native tooling only
npm ci
npm run mobile:scaffold
npm run mobile:sync
```

Tests cover authorization, cross-profile isolation, all visibility combinations, age/rating overrides, mandatory exclusions, approval, sample labels, import gating, budgets, price/private-state independence, migration, code rotation, persistence, and deletion. Chromium checks desktop parents, mobile children, illustrated search/categories, one-tap requests, approval, private purchases, and shared-link review.

## Scope and next integrations

This is a **single-family local prototype**, not a public multi-family service or compliance certification. There is no verified adult identity/parental consent service, live catalog/rating source, automatic price collection/alert delivery, or store release. Public deployment requires secure adult accounts and recovery, family isolation, HTTPS/session hardening, privacy policies, applicable legal/retailer checks, authoritative content classification, retention/deletion operations, and device testing. Never expose this local server publicly as-is.

Data is minimized to nicknames, optional age, wishes, chosen controls, catalog information, and private purchase planning. No analytics, advertising cookies, external images, or third-party assets run in the child experience. Family deletion removes profiles, wishes, prices, catalog and purchase data, and consent; the parent credential remains. External backups/snapshots need separate deletion handling.

Read the [product vision](docs/product-vision.md), [architecture and security boundaries](docs/architecture.md), and [mobile build guide](docs/mobile.md) for the implemented contracts and remaining release requirements.
