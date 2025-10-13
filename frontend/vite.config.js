import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configure Vite to emit source maps and disable minification when building
// in DEBUG/DEVELOPMENT mode. The Dockerfile sets the BUILD_MODE build-arg and
// exports it as an environment variable, so we read process.env.BUILD_MODE
// here to switch behaviors:
//   BUILD_MODE=development -> inline source maps + no minification
//   BUILD_MODE=production  -> optimized build (no source maps, minified)

const isDevBuild = (process.env.BUILD_MODE || process.env.NODE_ENV) === 'development'

export default defineConfig({
  plugins: [react()],
  build: {
    // 'inline' embeds the source map into the bundle which is handy for
    // debugging in environments where separate .map files may not be fetched.
    // This is the most robust option when serving built files from an nginx
    // runtime in a container.
    sourcemap: isDevBuild ? 'inline' : false,
    // Disable minification in development builds so stack traces and variable
    // names are preserved and easier to read. In production keep the default
    // minifier for optimized bundles.
    minify: isDevBuild ? false : 'esbuild'
  }
})
