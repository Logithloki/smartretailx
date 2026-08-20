# SmartRetailX Frontend Image / Asset Sources

## Retail photography

| Asset | Source provider | Original source | Usage | Licence/source note |
| --- | --- | --- | --- | --- |
| `frontend/public/images/storefront-hero.jpg` | Unsplash | [Kezen Zhang, shopping cart with groceries](https://unsplash.com/photos/a-person-pushing-a-shopping-cart-full-of-groceries-RJs8JDMdGdM) | Public storefront hero | Unsplash Licence; downloaded as an optimized local 1600px derivative so CloudFront serves a stable first-party asset. |

The storefront does not hotlink third-party images at runtime. Product API
responses currently have no image field, so product cards use an explicit
branded category illustration rather than fabricated product photography.

## Fonts

- **Plus Jakarta Sans** — Google Fonts, Open Font License.
- **JetBrains Mono** — Google Fonts, Open Font License.

## Future imagery policy

Use only sources that permit commercial reuse, such as Unsplash, Pexels,
Pixabay, or a per-file-verified Wikimedia Commons asset. Do not copy retailer
images, use search-engine thumbnails, or embed images with unclear licences.
Document every new source, URL, and licence note in this file when it is added.
