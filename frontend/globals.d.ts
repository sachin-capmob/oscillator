// Ambient declaration so the TypeScript language server recognizes CSS
// side-effect imports (e.g. `import "./globals.css"` in app/layout.tsx).
// Next.js handles these at build time via its webpack loader, but tsc/the
// editor need this stub to avoid a "Cannot find module" diagnostic.
declare module "*.css";
