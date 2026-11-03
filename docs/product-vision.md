# WishNest product vision

WishNest is a free Christmas wish-list app for iOS and Android, with one friendly discovery experience across participating retailers. Children should search, browse categories, see product pictures and permitted prices, and tap one large **Add to My Wish List** button. URLs and retailer websites are not the primary discovery flow.

Families choose their own browsing boundaries. Optional age information suggests default visibility, game ratings, wish approval, and product ordering. Parents can override those suggestions, including allowing an M-rated game for a younger child when permitted. Optional recommendations are separate from mandatory regional, retailer, platform, and app-safety eligibility restrictions, which cannot be overridden.

Each profile has independent price, budget, link, category, ESRB-rating, unverified-rating, and approval settings. Straightforward defaults come first; detailed settings live under Advanced. A parent can turn off age ordering entirely. Birth dates are not required.

Parents use a separate authenticated dashboard for permissions, budgets, authorized retailer comparisons, checkout links, approval requests, reservations, purchased gifts, actual paid amounts, and savings. Purchase state never changes the child's list, totals, rankings, or public price updates. Approved gifts remain visible after purchase. Pending requests remain outside the wish list and budget totals until approved.

The MVP preserves the working Python/SQLite backend and mobile web interface, rather than replacing completed permission, budget, wish, and privacy work. Capacitor packages that same interface into generated iOS/Android projects. The current native scaffolds are not signed release binaries and have no configured production backend.

## Honest MVP catalog

The default catalog contains 11 explicitly labeled fictional sample products, original local illustrations, categories, and made-up comparison prices. Amazon, Walmart, and Target names identify demonstration offer slots, not connected inventory. No sample offer has a checkout link. Sample ESRB ratings are marked unverified and require the parent's unverified-game setting. No scraping, retailer login, live product search, or credential assumptions are used.

Parents may also create manual catalog entries and ordinary product links. Such entries are labeled manual, not authorized/live retailer data. A link is not an integration, rating verification, or guarantee of stock. Product search runs inside the local catalog, without sending a child's search terms to a retailer. Approved sources can later populate the same catalog contracts and field-level projections.

## Optional import fallback

Manual link entry is parent-gated and supports normal Amazon.com, Walmart.com, and Target.com product URLs. The optional web Share Target stages a link in memory, clears it from the address bar, and requires adult login/review before importing. It never automatically fetches retailer metadata. Installed Android browsers that support Web Share Target may expose **Share to WishNest**; this is not implemented as an iOS/Android native share extension. OS/device installation has not been validated here. Primary discovery needs neither sharing nor pasted links.

## Funding and trust

Families pay nothing. Future optional adult affiliate links can generate commissions after program approval. They must be disclosed adjacent to links. Children receive ordinary product links only when permitted, never affiliate tracking. No targeted advertising, payment methods, in-app checkout, or automated purchasing is included.

Retailer price/catalog feeds, authoritative rating feeds, parent notification delivery, verified parental consent where required, multi-family hosting, privacy operations, native device testing, signing, and store publication remain external integration/release work. The local permission checkbox and access codes are useful prototype gates, not a legal-compliance certification or verified-adult identity system.
