import { spawnSync } from 'node:child_process'

export function seedScenario(action: 'async-states' | 'legacy-report', email: string, courseId: number) {
  const docker = process.env.E2E_DOCKER_EXE
  const container = process.env.E2E_CONTAINER_NAME
  if (!docker || !container) throw new Error('isolated seed environment is unavailable')
  const result = spawnSync(
    docker,
    ['exec', container, 'python', '/app/e2e/helpers/seed.py', action, email, String(courseId)],
    { encoding: 'utf8' },
  )
  if (result.status !== 0) throw new Error(`seed ${action} failed: ${result.stderr || result.stdout}`)
  return JSON.parse(result.stdout.trim()) as Record<string, string>
}
