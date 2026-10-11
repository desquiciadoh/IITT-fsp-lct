import { build } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
const res = await build({
  root: process.cwd(),
  logLevel: 'error',
  plugins: [react()],
  resolve: { alias: { '@': path.resolve('src') } },
  build: { write: false, sourcemap: false, minify: false },
})
const out = Array.isArray(res) ? res[0].output : res.output
for (const ch of out) {
  if (ch.type !== 'chunk') continue
  const srcs = ch.moduleIds.filter((m) => m.includes('/src/')).map((m) => path.relative(process.cwd(), m))
  const npm = [...new Set(ch.moduleIds.filter((m) => m.includes('node_modules')).map((m) => m.split('node_modules/')[1].split('/')[0] + '/' + (m.split('node_modules/')[1].split('/')[1] ?? '')))]
  console.log(`${(ch.code.length / 1024).toFixed(0)}KB entry:${ch.isEntry ? 'Y' : 'n'} dyn:${ch.isDynamicEntry ? 'Y' : 'n'} ${ch.fileName}\n   src: ${srcs.slice(0, 6).join(', ')}\n   npm(top): ${npm.slice(0, 8).join(', ')}`)
}
