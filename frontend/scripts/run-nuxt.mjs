import { copyFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawn } from 'node:child_process'

if (process.platform === 'win32') {
  const binary = resolve('node_modules/@esbuild/win32-x64/esbuild.exe')
  const packagePath = resolve('node_modules/esbuild/package.json')

  // Synced Windows volumes can prohibit launching executables in node_modules.
  if (existsSync(binary) && existsSync(packagePath)) {
    const { version } = JSON.parse(readFileSync(packagePath, 'utf8'))
    const target = join(tmpdir(), 'zevent-frontend', 'esbuild', version, 'esbuild.exe')
    mkdirSync(resolve(target, '..'), { recursive: true })
    copyFileSync(binary, target)
    process.env.ESBUILD_BINARY_PATH = target
  }
}

const nuxt = resolve('node_modules/nuxt/bin/nuxt.mjs')
const child = spawn(process.execPath, [nuxt, ...process.argv.slice(2)], {
  env: process.env,
  stdio: 'inherit',
})

child.on('error', (error) => {
  console.error(error)
  process.exitCode = 1
})
child.on('exit', (code) => {
  process.exitCode = code ?? 1
})
