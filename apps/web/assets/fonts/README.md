# Fonts for generated images

`Geist-Regular.ttf` and `Geist-SemiBold.ttf` are used only by `opengraph-image.tsx`
(Satori cannot read `woff2`). The page itself loads Geist through `next/font/google`.

- Source: npm package `geist@1.7.2` (published from the official `vercel/geist-font` repo),
  files `dist/fonts/geist-sans/Geist-Regular.ttf` and `Geist-SemiBold.ttf`, copied unmodified.
- SHA-256: Regular `5c8968eafb98a4c4f47033daf29e38e284a6f2a82eb017d171ab040fe7c4b615`,
  SemiBold `612ec98df33935354f39e81e54101656961ab6e5549f64b63eb57868ba7bab8d`.
- License: SIL Open Font License 1.1, see `OFL.txt` (copied from the package's `LICENSE.txt`).
